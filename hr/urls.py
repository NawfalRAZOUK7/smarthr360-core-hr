from django.urls import path

from .views import (
    DepartmentDetailView,
    DepartmentListCreateView,
    EmployeeDetailView,
    EmployeeListCreateView,
    EmployeeMeView,
    EmployeeSkillDetailView,
    EmployeeSkillListCreateView,
    FutureCompetencyDetailView,
    FutureCompetencyListCreateView,
    MyTeamListView,
    SkillDetailView,
    SkillListCreateView,
)

urlpatterns = [
    # Departments
    path("departments/", DepartmentListCreateView.as_view(), name="hr-department-list"),
    path("departments/<int:pk>/", DepartmentDetailView.as_view(), name="hr-department-detail"),

    # Employees
    path("employees/me/", EmployeeMeView.as_view(), name="hr-employee-me"),
    path("employees/my-team/", MyTeamListView.as_view(), name="hr-employee-my-team"),
    path("employees/", EmployeeListCreateView.as_view(), name="hr-employee-list"),
    path("employees/<int:pk>/", EmployeeDetailView.as_view(), name="hr-employee-detail"),

    # Skills catalog
    path("skills/", SkillListCreateView.as_view(), name="hr-skill-list"),
    path("skills/<int:pk>/", SkillDetailView.as_view(), name="hr-skill-detail"),

    # Employee skills
    path("employee-skills/", EmployeeSkillListCreateView.as_view(), name="hr-employee-skill-list"),
    path("employee-skills/<int:pk>/", EmployeeSkillDetailView.as_view(), name="hr-employee-skill-detail"),

    # Future competencies
    path(
        "future-competencies/",
        FutureCompetencyListCreateView.as_view(),
        name="hr-future-competency-list",
    ),
    path(
        "future-competencies/<int:pk>/",
        FutureCompetencyDetailView.as_view(),
        name="hr-future-competency-detail",
    ),
]
