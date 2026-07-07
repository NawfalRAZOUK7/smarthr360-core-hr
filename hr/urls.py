from django.urls import path

from .interop.views import (
    CompetencyDefinitionsView,
    PersonCompetenciesView,
    PositionCompetencyModelsView,
)
from .org_api import EmployeeExportView, OrgChartView, SkillMatrixView
from .prediction.views import SkillGapPredictionView
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
    # Organization insights
    path("org-chart/", OrgChartView.as_view(), name="hr-org-chart"),
    path("skill-matrix/", SkillMatrixView.as_view(), name="hr-skill-matrix"),
    path("employees/export/", EmployeeExportView.as_view(), name="hr-employee-export"),

    # Interoperability — HR Open Standards (Étape 3)
    path(
        "interop/competency-definitions/",
        CompetencyDefinitionsView.as_view(),
        name="hr-interop-competency-definitions",
    ),
    path(
        "interop/person-competencies/",
        PersonCompetenciesView.as_view(),
        name="hr-interop-person-competencies",
    ),
    path(
        "interop/position-competency-models/",
        PositionCompetencyModelsView.as_view(),
        name="hr-interop-position-competency-models",
    ),

    # Predictions — Skill Gaps (Étape 4)
    path(
        "predictions/skill-gaps/",
        SkillGapPredictionView.as_view(),
        name="hr-predictions-skill-gaps",
    ),

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
