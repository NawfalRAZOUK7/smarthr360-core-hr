"""Review templates and 360° peer feedback."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer, ValidationError
from rest_framework.views import APIView

from smarthr360_jwt_auth.access import has_hr_access

from config.api_mixins import ApiResponseMixin
from hr.identity import get_own_profile

from .models import PeerFeedback, PerformanceReview, ReviewTemplate


class ReviewTemplateSerializer(ModelSerializer):
    class Meta:
        model = ReviewTemplate
        fields = [
            "id", "name", "description", "items", "is_active",
            "created_by_user_id", "created_at", "updated_at",
        ]
        read_only_fields = ["created_by_user_id", "created_at", "updated_at"]

    def validate_items(self, value):
        if not isinstance(value, list) or not value:
            raise ValidationError("items must be a non-empty list.")
        for entry in value:
            if not isinstance(entry, dict) or not entry.get("criteria"):
                raise ValidationError(
                    'each item must be {"criteria": str, "weight": int?}.'
                )
            weight = entry.get("weight", 1)
            if not isinstance(weight, int) or weight < 1:
                raise ValidationError("weight must be a positive integer.")
        return value


class ReviewTemplateListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    queryset = ReviewTemplate.objects.filter(is_active=True)
    serializer_class = ReviewTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # permission BEFORE payload validation: a non-HR caller gets 403
        # regardless of body shape
        if not has_hr_access(request.user):
            raise PermissionDenied("Only HR or Admin can create review templates.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by_user_id=self.request.user.id)


class ReviewTemplateDetailView(ApiResponseMixin,
                               generics.RetrieveUpdateDestroyAPIView):
    queryset = ReviewTemplate.objects.all()
    serializer_class = ReviewTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method not in permissions.SAFE_METHODS and not has_hr_access(
            request.user
        ):
            raise PermissionDenied("Only HR or Admin can modify review templates.")


def apply_template(review: PerformanceReview, template: ReviewTemplate) -> int:
    """Pre-create unrated ReviewItems from a template. Returns count."""
    from .models import ReviewItem

    created = [
        ReviewItem(
            review=review,
            criteria=entry["criteria"],
            weight=entry.get("weight", 1),
            score=None,
        )
        for entry in template.items
    ]
    ReviewItem.objects.bulk_create(created)
    return len(created)


class PeerFeedbackView(ApiResponseMixin, APIView):
    """POST/GET /api/reviews/<id>/feedback/ — 360° feedback.

    Submit: any authenticated employee EXCEPT the reviewee; one entry
    per reviewer per review.
    Read: the reviewee (and their manager) see aggregates + anonymized
    comments; HR sees the full attributed list.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, review_id):
        review = get_object_or_404(PerformanceReview, pk=review_id)
        user = request.user

        if review.employee.user_id == user.id:
            raise PermissionDenied("You cannot give 360° feedback on yourself.")

        try:
            rating = int(request.data.get("rating", 0))
        except (TypeError, ValueError):
            rating = 0
        if not 1 <= rating <= 5:
            return Response(
                {"detail": "rating must be an integer between 1 and 5."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        relationship = request.data.get("relationship", "PEER")
        if relationship not in PeerFeedback.Relationship.values:
            return Response(
                {"detail": f"relationship must be one of "
                           f"{list(PeerFeedback.Relationship.values)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if PeerFeedback.objects.filter(
            review=review, reviewer_user_id=user.id
        ).exists():
            return Response(
                {"detail": "You already gave feedback on this review."},
                status=status.HTTP_409_CONFLICT,
            )

        PeerFeedback.objects.create(
            review=review,
            reviewer_user_id=user.id,
            relationship=relationship,
            rating=rating,
            comment=request.data.get("comment", ""),
        )
        return Response(
            {"detail": "Feedback recorded.", "review_id": review.id},
            status=status.HTTP_201_CREATED,
        )

    def get(self, request, review_id):
        review = get_object_or_404(PerformanceReview, pk=review_id)
        user = request.user

        is_reviewee = review.employee.user_id == user.id
        own_profile = get_own_profile(user)
        is_review_manager = (
            review.manager_id is not None
            and own_profile is not None
            and review.manager_id == own_profile.id
        )
        if not (is_reviewee or is_review_manager or has_hr_access(user)):
            raise PermissionDenied("Not your review.")

        entries = list(review.peer_feedback.all())
        ratings = [entry.rating for entry in entries]
        payload = {
            "review_id": review.id,
            "count": len(entries),
            "average_rating": round(sum(ratings) / len(ratings), 2)
            if ratings else None,
            "by_relationship": {
                rel: len([e for e in entries if e.relationship == rel])
                for rel in PeerFeedback.Relationship.values
            },
            # anonymized for everyone…
            "comments": [
                {"relationship": e.relationship, "rating": e.rating,
                 "comment": e.comment}
                for e in entries if e.comment
            ],
        }
        # …attribution for HR only (auditability)
        if has_hr_access(user):
            payload["attributed"] = [
                {"reviewer_user_id": e.reviewer_user_id,
                 "relationship": e.relationship, "rating": e.rating,
                 "comment": e.comment}
                for e in entries
            ]
        return Response(payload)
