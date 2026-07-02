# reviews/views.py
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from smarthr360_jwt_auth.access import has_hr_access, has_manager_access, is_auditor, is_manager
from hr.models import EmployeeProfile
from config.api_mixins import ApiResponseMixin
from hr.identity import get_own_profile

from .models import Goal, PerformanceReview, ReviewCycle, ReviewItem
from .serializers import (
    GoalSerializer,
    PerformanceReviewSerializer,
    ReviewCycleSerializer,
    ReviewItemSerializer,
)


class ReviewCycleListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    """
    GET  /api/reviews/cycles/   → list all cycles (any authenticated)
    POST /api/reviews/cycles/   → create cycle (HR or ADMIN)
    """
    queryset = ReviewCycle.objects.all()
    serializer_class = ReviewCycleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user
        if not has_hr_access(user):
            raise PermissionDenied("Only HR or Admin can create review cycles.")
        serializer.save()


class ReviewCycleDetailView(ApiResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET   /api/reviews/cycles/<id>/
    PATCH /api/reviews/cycles/<id>/   → HR or ADMIN
    """
    queryset = ReviewCycle.objects.all()
    serializer_class = ReviewCycleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        user = self.request.user
        if not has_hr_access(user):
            raise PermissionDenied("Only HR or Admin can update review cycles.")
        serializer.save()


def _reviews_queryset_for_user(user):
    qs = PerformanceReview.objects.select_related(
        "employee",
        "employee__department",
        "manager",
        "cycle",
    ).prefetch_related("items")

    # HR & Admin → all reviews
    if has_hr_access(user) or is_auditor(user):
        return qs

    # Manager → reviews where they are the manager
    if is_manager(user) and get_own_profile(user) is not None:
        return qs.filter(manager=get_own_profile(user))

    # Employee → only own reviews
    if get_own_profile(user) is not None:
        return qs.filter(employee__user_id=user.id)

    return qs.none()


class PerformanceReviewListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    """
    GET  /api/reviews/
        HR/Admin → all
        Manager  → their team reviews
        Employee → own reviews

    POST /api/reviews/
        Manager / HR / Admin → create review
    """
    serializer_class = PerformanceReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return _reviews_queryset_for_user(self.request.user)

    def perform_create(self, serializer):
        user = self.request.user

        if not has_manager_access(user):
            raise PermissionDenied("Only Manager, HR or Admin can create reviews.")

        employee_id = self.request.data.get("employee_id")
        cycle_id = self.request.data.get("cycle_id")

        if not employee_id or not cycle_id:
            raise ValidationError({"detail": "employee_id and cycle_id are required."})

        employee = get_object_or_404(EmployeeProfile, pk=employee_id)
        cycle = get_object_or_404(ReviewCycle, pk=cycle_id)

        # Determine manager for this review
        manager = None
        if is_manager(user) and get_own_profile(user) is not None:
            manager_profile = get_own_profile(user)

            # STRICT RULE:
            # Manager can ONLY review employees that have them as manager.
            if employee.manager_id != manager_profile.id:
                raise PermissionDenied("You can only review employees in your team.")

            manager = manager_profile
        else:
            # HR/Admin: optional manager override if provided, otherwise use employee.manager
            manager_id = self.request.data.get("manager")
            if manager_id:
                manager = get_object_or_404(EmployeeProfile, pk=manager_id)
            else:
                manager = employee.manager

        review = serializer.save(
            employee=employee,
            manager=manager,
            cycle=cycle,
        )
        # overall_score will be computed later when items are added
        return review


class PerformanceReviewDetailView(ApiResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET   /api/reviews/<id>/
    PATCH /api/reviews/<id>/
        - Manager: can edit if DRAFT
        - HR/Admin: can always edit
        - Employee: can update only employee_comment when DRAFT
    """
    serializer_class = PerformanceReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return _reviews_queryset_for_user(self.request.user)

    def get_object(self):
        # Fetch without filtering so we can return 403 instead of 404 on permission issues
        review = get_object_or_404(
            PerformanceReview.objects.select_related(
                "employee", "manager", "cycle"
            ),
            pk=self.kwargs.get(self.lookup_field or "pk"),
        )

        user = self.request.user
        if has_hr_access(user):
            return review

        if is_auditor(user) and self.request.method in permissions.SAFE_METHODS:
            return review

        if (
            is_manager(user)
            and get_own_profile(user) is not None
            and review.manager_id == get_own_profile(user).id
        ):
            return review

        if get_own_profile(user) is not None and review.employee.user_id == user.id:
            return review

        raise PermissionDenied("You do not have permission to access this review.")

    def perform_update(self, serializer):
        user = self.request.user
        review = self.get_object()

        # HR/Admin → can always update
        if has_hr_access(user):
            serializer.save()
            return

        # Manager → can update only if they are the manager AND review is DRAFT
        if (
            is_manager(user)
            and get_own_profile(user) is not None
            and review.manager_id == get_own_profile(user).id
            and review.status == PerformanceReview.Status.DRAFT
        ):
            serializer.save()
            return

        # Employee → can only update their own employee_comment while DRAFT
        if (
            get_own_profile(user) is not None
            and review.employee.user_id == user.id
            and review.status == PerformanceReview.Status.DRAFT
        ):
            allowed = {"employee_comment"}
            for field in list(serializer.validated_data.keys()):
                if field not in allowed:
                    serializer.validated_data.pop(field)
            serializer.save()
            return

        raise PermissionDenied("You do not have permission to update this review.")


class PerformanceReviewSubmitView(ApiResponseMixin, APIView):
    """
    POST /api/reviews/<id>/submit/
    Manager (or HR/Admin) submits a DRAFT review → SUBMITTED
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        review = get_object_or_404(PerformanceReview, pk=pk)
        user = request.user

        # HR/Admin can submit
        if not has_hr_access(user):
            # Managers can submit only their own reviews
            if not (
                is_manager(user)
                and get_own_profile(user) is not None
                and review.manager_id == get_own_profile(user).id
            ):
                raise PermissionDenied("You cannot submit this review.")

        if review.status != PerformanceReview.Status.DRAFT:
            raise ValidationError({"detail": "Only DRAFT reviews can be submitted."})

        review.status = PerformanceReview.Status.SUBMITTED
        manager_comment = request.data.get("manager_comment")
        if manager_comment is not None:
            review.manager_comment = manager_comment
        review.save(update_fields=["status", "manager_comment"])

        # ApiResponseMixin will wrap this into { data: {...}, meta: {...} }
        return Response(
            {"detail": "Review submitted.", "status": review.status},
            status=status.HTTP_200_OK,
        )


class PerformanceReviewAcknowledgeView(ApiResponseMixin, APIView):
    """
    POST /api/reviews/<id>/acknowledge/
    Employee acknowledges a SUBMITTED review → COMPLETED
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        review = get_object_or_404(PerformanceReview, pk=pk)
        user = request.user

        if not get_own_profile(user) is not None or review.employee.user_id != user.id:
            raise PermissionDenied("You can only acknowledge your own reviews.")

        if review.status != PerformanceReview.Status.SUBMITTED:
            raise ValidationError({"detail": "Only SUBMITTED reviews can be acknowledged."})

        emp_comment = request.data.get("employee_comment")
        if emp_comment is not None:
            review.employee_comment = emp_comment

        review.status = PerformanceReview.Status.COMPLETED
        review.save(update_fields=["status", "employee_comment"])

        return Response(
            {"detail": "Review acknowledged.", "status": review.status},
            status=status.HTTP_200_OK,
        )


class ReviewItemListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    """
    GET  /api/reviews/<review_id>/items/
        → list items of a review (same visibility as review)

    POST /api/reviews/<review_id>/items/
        → Manager / HR / Admin add items when review is DRAFT
    """
    serializer_class = ReviewItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _get_review(self):
        review_id = self.kwargs.get("review_id")
        return get_object_or_404(PerformanceReview, pk=review_id)

    def get_queryset(self):
        user = self.request.user
        review = self._get_review()
        qs = ReviewItem.objects.filter(review=review)

        if has_hr_access(user):
            return qs

        if is_auditor(user):
            return qs

        if (
            is_manager(user)
            and get_own_profile(user) is not None
            and review.manager_id == get_own_profile(user).id
        ):
            return qs

        if get_own_profile(user) is not None and review.employee.user_id == user.id:
            return qs

        return ReviewItem.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        review = self._get_review()

        if review.status != PerformanceReview.Status.DRAFT:
            raise ValidationError({"detail": "Items can only be added to DRAFT reviews."})

        if not has_hr_access(user):
            if not (
                is_manager(user)
                and get_own_profile(user) is not None
                and review.manager_id == get_own_profile(user).id
            ):
                raise PermissionDenied("You cannot add items to this review.")

        item = serializer.save(review=review)
        review.recalculate_overall_score()
        return item


class ReviewItemDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/reviews/items/<id>/
        same access rules as parent review
    """
    serializer_class = ReviewItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ReviewItem.objects.select_related("review", "review__employee")

        if has_hr_access(user):
            return qs

        base_reviews = _reviews_queryset_for_user(user)
        return qs.filter(review__in=base_reviews)

    def perform_update(self, serializer):
        item = self.get_object()
        review = item.review
        user = self.request.user

        if review.status != PerformanceReview.Status.DRAFT:
            raise ValidationError({"detail": "Items can only be edited on DRAFT reviews."})

        if not has_hr_access(user):
            if not (
                is_manager(user)
                and get_own_profile(user) is not None
                and review.manager_id == get_own_profile(user).id
            ):
                raise PermissionDenied("You cannot edit this item.")

        serializer.save()
        review.recalculate_overall_score()

    def perform_destroy(self, instance):
        review = instance.review
        user = self.request.user

        if review.status != PerformanceReview.Status.DRAFT:
            raise ValidationError({"detail": "Items can only be deleted on DRAFT reviews."})

        if not has_hr_access(user):
            if not (
                is_manager(user)
                and get_own_profile(user) is not None
                and review.manager_id == get_own_profile(user).id
            ):
                raise PermissionDenied("You cannot delete this item.")

        super().perform_destroy(instance)
        review.recalculate_overall_score()


def _goals_queryset_for_user(user):
    qs = Goal.objects.select_related("employee", "cycle")

    if has_hr_access(user) or is_auditor(user):
        return qs

    if is_manager(user) and get_own_profile(user) is not None:
        manager_profile = get_own_profile(user)
        return qs.filter(employee__manager=manager_profile)

    if get_own_profile(user) is not None:
        return qs.filter(employee__user_id=user.id)

    return qs.none()


class GoalListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    """
    GET  /api/reviews/goals/
        HR/Admin → all
        Manager  → team goals
        Employee → own goals

    POST /api/reviews/goals/
        - Employee: can create own goals
        - Manager: can create for team members
        - HR/Admin: can create for any employee
    """
    serializer_class = GoalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = _goals_queryset_for_user(self.request.user)

        employee_id = self.request.query_params.get("employee_id")
        cycle_id = self.request.query_params.get("cycle_id")

        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        employee_id = self.request.data.get("employee_id")
        cycle_id = self.request.data.get("cycle_id")

        # Employee creating their own goal → employee_id optional
        if not employee_id and get_own_profile(user) is not None:
            employee = get_own_profile(user)
        elif employee_id:
            employee = get_object_or_404(EmployeeProfile, pk=employee_id)
        else:
            raise ValidationError({"detail": "employee_id is required."})

        # Permissions
        if has_hr_access(user):
            pass
        elif is_manager(user) and get_own_profile(user) is not None:
            if employee.manager_id != get_own_profile(user).id:
                raise PermissionDenied("Managers can only create goals for their team.")
        elif get_own_profile(user) is not None:
            if employee.user_id != user.id:
                raise PermissionDenied("You can only create your own goals.")
        else:
            raise PermissionDenied("Not allowed to create goals.")

        cycle = None
        if cycle_id:
            cycle = get_object_or_404(ReviewCycle, pk=cycle_id)

        serializer.save(
            employee=employee,
            cycle=cycle,
            created_by_user_id=user.id,
        )


class GoalDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/reviews/goals/<id>/
        - HR/Admin: any
        - Manager: team goals
        - Employee: own goals
    """
    serializer_class = GoalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return _goals_queryset_for_user(self.request.user)

    def get_object(self):
        goal = get_object_or_404(
            Goal.objects.select_related("employee__manager"),
            pk=self.kwargs.get(self.lookup_field or "pk"),
        )
        user = self.request.user

        if has_hr_access(user):
            return goal

        if is_auditor(user) and self.request.method in permissions.SAFE_METHODS:
            return goal

        if is_manager(user) and get_own_profile(user) is not None:
            if goal.employee.manager_id == get_own_profile(user).id:
                return goal
            raise PermissionDenied("You cannot access this goal.")

        if get_own_profile(user) is not None and goal.employee.user_id == user.id:
            return goal

        raise PermissionDenied("You cannot access this goal.")

    def perform_update(self, serializer):
        user = self.request.user
        goal = self.get_object()

        # HR/Admin → full rights
        if has_hr_access(user):
            serializer.save()
            return

        # Manager → team goals only
        if is_manager(user) and get_own_profile(user) is not None:
            if goal.employee.manager_id != get_own_profile(user).id:
                raise PermissionDenied("You cannot update this goal.")
            serializer.save()
            return

        # Employee → own goals only
        if get_own_profile(user) is not None and goal.employee.user_id == user.id:
            serializer.save()
            return

        raise PermissionDenied("You cannot update this goal.")

    def perform_destroy(self, instance):
        user = self.request.user
        goal = instance

        if has_hr_access(user):
            return super().perform_destroy(instance)

        if is_manager(user) and get_own_profile(user) is not None:
            if goal.employee.manager_id != get_own_profile(user).id:
                raise PermissionDenied("You cannot delete this goal.")
            return super().perform_destroy(instance)

        if get_own_profile(user) is not None and goal.employee.user_id == user.id:
            return super().perform_destroy(instance)

        raise PermissionDenied("You cannot delete this goal.")
