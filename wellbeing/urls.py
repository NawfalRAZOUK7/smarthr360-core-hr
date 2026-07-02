from django.urls import path

from .views import (
    SurveyQuestionDetailView,
    SurveyQuestionListCreateView,
    SurveyStatsView,
    SurveySubmitView,
    TeamStatsView,
    WellbeingSurveyDetailView,
    WellbeingSurveyListCreateView,
)

urlpatterns = [
    # surveys
    path("surveys/", WellbeingSurveyListCreateView.as_view(), name="wellbeing-survey-list"),
    path("surveys/<int:pk>/", WellbeingSurveyDetailView.as_view(), name="wellbeing-survey-detail"),

    # questions
    path(
        "surveys/<int:survey_id>/questions/",
        SurveyQuestionListCreateView.as_view(),
        name="wellbeing-question-list",
    ),
    path(
        "questions/<int:pk>/",
        SurveyQuestionDetailView.as_view(),
        name="wellbeing-question-detail",
    ),

    # employee submission
    path(
        "surveys/<int:survey_id>/submit/",
        SurveySubmitView.as_view(),
        name="wellbeing-survey-submit",
    ),

    # stats
    path(
        "surveys/<int:survey_id>/stats/",
        SurveyStatsView.as_view(),
        name="wellbeing-survey-stats",
    ),
    path(
        "surveys/<int:survey_id>/team-stats/",
        TeamStatsView.as_view(),
        name="wellbeing-team-stats",
    ),
]
