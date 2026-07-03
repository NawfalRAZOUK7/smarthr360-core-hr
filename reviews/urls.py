# reviews/urls.py
from django.urls import path

from .feedback_api import (
    PeerFeedbackView,
    ReviewTemplateDetailView,
    ReviewTemplateListCreateView,
)
from .views import (
    GoalDetailView,
    GoalListCreateView,
    PerformanceReviewAcknowledgeView,
    PerformanceReviewDetailView,
    PerformanceReviewListCreateView,
    PerformanceReviewSubmitView,
    ReviewCycleDetailView,
    ReviewCycleListCreateView,
    ReviewItemDetailView,
    ReviewItemListCreateView,
)

urlpatterns = [
    # review templates + 360 feedback
    path("templates/", ReviewTemplateListCreateView.as_view(), name="review-template-list"),
    path("templates/<int:pk>/", ReviewTemplateDetailView.as_view(), name="review-template-detail"),
    path("<int:review_id>/feedback/", PeerFeedbackView.as_view(), name="review-feedback"),

    # cycles
    path("cycles/", ReviewCycleListCreateView.as_view(), name="review-cycle-list"),
    path("cycles/<int:pk>/", ReviewCycleDetailView.as_view(), name="review-cycle-detail"),

    # reviews
    path("", PerformanceReviewListCreateView.as_view(), name="review-list"),
    path("<int:pk>/", PerformanceReviewDetailView.as_view(), name="review-detail"),
    path("<int:pk>/submit/", PerformanceReviewSubmitView.as_view(), name="review-submit"),
    path(
        "<int:pk>/acknowledge/",
        PerformanceReviewAcknowledgeView.as_view(),
        name="review-acknowledge",
    ),

    # review items
    path("<int:review_id>/items/", ReviewItemListCreateView.as_view(), name="reviewitem-list"),
    path("items/<int:pk>/", ReviewItemDetailView.as_view(), name="reviewitem-detail"),

    # goals
    path("goals/", GoalListCreateView.as_view(), name="goal-list"),
    path("goals/<int:pk>/", GoalDetailView.as_view(), name="goal-detail"),
]
