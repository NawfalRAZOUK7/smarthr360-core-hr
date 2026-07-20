from rest_framework import serializers

from reviews.models import Goal

from .models import Department, EmployeeDocument, EmployeeProfile, EmployeeSkill, FutureCompetency, Notification, Skill, TrainingAction


class IdentitySerializer(serializers.Serializer):
    """Read-only identity snapshot stored on the profile (replaces the
    legacy nested accounts.UserSerializer — identity now lives in the
    auth service; we expose the denormalized snapshot)."""

    id = serializers.IntegerField(source="user_id", read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    role = serializers.CharField(source="user_role", read_only=True)


class DepartmentSerializer(serializers.ModelSerializer):
    """
    Canonical representation of a department.
    Used everywhere in HR / reviews / wellbeing when we need department info.
    """

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "code",
            "description",
        ]


class EmployeeProfileSerializer(serializers.ModelSerializer):
    """
    Canonical representation of an employee profile.

    READ:
      - user: identity snapshot (user_id/email/name/role)
      - department: DepartmentSerializer
    WRITE:
      - department_id: PK of Department
      - manager_id: PK of EmployeeProfile (manager)
    """

    user = IdentitySerializer(source="*", read_only=True)
    department = DepartmentSerializer(read_only=True)

    department_id = serializers.PrimaryKeyRelatedField(
        source="department",
        queryset=Department.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    manager_id = serializers.PrimaryKeyRelatedField(
        source="manager",
        queryset=EmployeeProfile.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = EmployeeProfile
        fields = [
            "id",
            "user",
            "user_id",
            "email",
            "first_name",
            "last_name",
            "user_role",
            "department",
            "department_id",
            "manager_id",
            "job_title",
            "employment_type",
            "hire_date",
            "date_of_birth",
            "phone_number",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
        ]


class EmployeeSelfUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer used when an EMPLOYEE updates their own profile.
    Only allows 'safe' personal fields.
    """

    class Meta:
        model = EmployeeProfile
        fields = [
            "phone_number",
            "date_of_birth",
        ]


class SkillSerializer(serializers.ModelSerializer):
    """
    Canonical representation of a skill.
    """

    # BooleanField defaults to False when omitted; explicitly default to True so new skills are active
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
            "code",
            "description",
            "category",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
        ]


class EmployeeSkillSerializer(serializers.ModelSerializer):
    """
    Representation of a skill evaluation for an employee.

    READ:
      - employee: EmployeeProfileSerializer (canonical employee object)
      - skill: SkillSerializer
      - last_evaluated_by_user_id: auth user id of the evaluator

    WRITE:
      - employee_id: optional helper when not using the HR view logic directly
      - skill_id: same
      (But in your views, you typically resolve employee/skill manually.)
    """

    employee_id = serializers.IntegerField(write_only=True, required=False)
    skill_id = serializers.IntegerField(write_only=True, required=False)

    employee = EmployeeProfileSerializer(read_only=True)
    skill = SkillSerializer(read_only=True)

    class Meta:
        model = EmployeeSkill
        fields = [
            "id",
            "employee_id",
            "skill_id",
            "employee",
            "skill",
            "level",
            "target_level",
            "last_evaluated_by_user_id",
            "last_evaluated_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "employee",
            "skill",
            "last_evaluated_by_user_id",
            "last_evaluated_at",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        """
        Optional small safeguard:
        If someone uses the serializer directly with employee_id/skill_id
        (outside of your views logic), you can validate their presence/format here.
        We keep this light to not conflict with the logic in views.
        """
        return super().validate(attrs)


class FutureCompetencySerializer(serializers.ModelSerializer):
    """
    Representation of a future competency need.

    READ:
      - skill: SkillSerializer
      - department: DepartmentSerializer (or null)

    WRITE:
      - skill_id: required (view can enforce it)
      - department_id: optional (if company-wide competency)
    """

    skill_id = serializers.IntegerField(write_only=True, required=False)
    department_id = serializers.IntegerField(write_only=True, required=False)

    skill = SkillSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)

    class Meta:
        model = FutureCompetency
        fields = [
            "id",
            "skill_id",
            "department_id",
            "skill",
            "department",
            "timeframe",
            "importance",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "skill",
            "department",
            "created_at",
            "updated_at",
        ]


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    is_expiring_soon = serializers.BooleanField(read_only=True)

    class Meta:
        model = EmployeeDocument
        fields = [
            "id", "employee", "doc_type", "title", "reference_url",
            "issue_date", "expiry_date", "uploaded_by_user_id",
            "is_expiring_soon", "created_at",
        ]
        read_only_fields = ["employee", "uploaded_by_user_id", "created_at"]


class TrainingActionSerializer(serializers.ModelSerializer):
    """A trackable plan to close a skill gap (course + owner + due date + status)."""

    skill_id = serializers.PrimaryKeyRelatedField(
        source="skill", queryset=Skill.objects.all(), write_only=True
    )
    department_id = serializers.PrimaryKeyRelatedField(
        source="department", queryset=Department.objects.all(),
        write_only=True, required=False, allow_null=True,
    )
    employee_id = serializers.PrimaryKeyRelatedField(
        source="employee", queryset=EmployeeProfile.objects.all(),
        write_only=True, required=False, allow_null=True,
    )
    goal_id = serializers.PrimaryKeyRelatedField(
        source="goal", queryset=Goal.objects.all(),
        write_only=True, required=False, allow_null=True,
    )
    skill = serializers.SerializerMethodField(read_only=True)
    department = serializers.SerializerMethodField(read_only=True)
    employee = serializers.SerializerMethodField(read_only=True)
    goal = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TrainingAction
        fields = [
            "id", "title", "provider",
            "skill", "skill_id", "department", "department_id", "employee", "employee_id",
            "goal", "goal_id",
            "owner_user_id", "target_level", "due_date", "budget",
            "status", "progress_percent", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_skill(self, obj):
        if not obj.skill_id:
            return None
        return {"id": obj.skill_id, "name": obj.skill.name, "code": obj.skill.code}

    def get_department(self, obj):
        if not obj.department_id:
            return None
        return {"id": obj.department_id, "name": obj.department.name}

    def get_employee(self, obj):
        if not obj.employee_id:
            return None
        e = obj.employee
        return {"id": obj.employee_id, "name": f"{e.first_name} {e.last_name}".strip() or e.email}

    def get_goal(self, obj):
        if not obj.goal_id:
            return None
        return {"id": obj.goal_id, "title": obj.goal.title, "status": obj.goal.status}


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "user_id", "type", "title", "body", "link", "read", "created_at"]
        read_only_fields = ["id", "read", "created_at"]
