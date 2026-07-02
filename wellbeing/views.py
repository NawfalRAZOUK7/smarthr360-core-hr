import json

# wellbeing/views.py (UPDATED WITH ENVELOPE)
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView

from smarthr360_jwt_auth.access import has_hr_access, is_auditor, is_manager
from hr.models import EmployeeProfile
from config.api_mixins import ApiResponseMixin
from hr.identity import get_own_profile

from .models import SurveyQuestion, SurveyResponse, WellbeingSurvey
from .serializers import (
    SurveyQuestionSerializer,
    SurveyStatsSerializer,
    SurveySubmissionSerializer,
    TeamStatsSerializer,
    WellbeingSurveySerializer,
)


class WellbeingSurveyListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    queryset = WellbeingSurvey.objects.all()
    serializer_class = WellbeingSurveySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user
        if not has_hr_access(user):
            raise PermissionDenied("Only HR or Admin can create wellbeing surveys.")
        serializer.save(created_by_user_id=user.id)


class WellbeingSurveyDetailView(ApiResponseMixin, generics.RetrieveUpdateAPIView):
    queryset = WellbeingSurvey.objects.all()
    serializer_class = WellbeingSurveySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        user = self.request.user
        if not has_hr_access(user):
            raise PermissionDenied("Only HR or Admin can update wellbeing surveys.")
        serializer.save()


class SurveyQuestionListCreateView(ApiResponseMixin, generics.ListCreateAPIView):
    serializer_class = SurveyQuestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_survey(self):
        survey_id = self.kwargs.get("survey_id")
        return get_object_or_404(WellbeingSurvey, pk=survey_id)

    def get_queryset(self):
        return SurveyQuestion.objects.filter(survey=self.get_survey())

    def perform_create(self, serializer):
        user = self.request.user
        if not has_hr_access(user):
            raise PermissionDenied("Only HR or Admin can add questions.")
        serializer.save(survey=self.get_survey())


class SurveyQuestionDetailView(ApiResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = SurveyQuestion.objects.select_related("survey")
    serializer_class = SurveyQuestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        user = self.request.user
        if not has_hr_access(user):
            raise PermissionDenied("Only HR or Admin can update questions.")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not has_hr_access(user):
            raise PermissionDenied("Only HR or Admin can delete questions.")
        super().perform_destroy(instance)


class SurveySubmitView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, survey_id):
        survey = get_object_or_404(WellbeingSurvey, pk=survey_id, is_active=True)

        # Accept form-encoded payloads where "answers" may arrive as a JSON string
        base_request = getattr(request, "_request", request)

        # Capture raw body before request.data consumes the stream
        parsed_body = None
        try:
            raw_body = getattr(base_request, "_body", None)
            if raw_body is None and hasattr(base_request, "body"):
                raw_body = base_request.body
            if raw_body:
                if isinstance(raw_body, bytes):
                    raw_body = raw_body.decode()
                parsed_body = json.loads(raw_body)
        except Exception:
            parsed_body = None

        incoming_data = request.data
        answers_value = incoming_data.get("answers")

        if isinstance(parsed_body, dict) and isinstance(parsed_body.get("answers"), dict):
            incoming_data = parsed_body
            answers_value = parsed_body.get("answers")

        # Handle form-encoded keys like answers[<id>]=value when "answers" isn't present
        if answers_value is None and hasattr(incoming_data, "items"):
            reconstructed = {}
            for key, value in incoming_data.items():
                if isinstance(key, str) and key.startswith("answers[") and key.endswith("]"):
                    qid = key[len("answers[") : -1]
                    reconstructed[qid] = value
            if reconstructed:
                mutable = incoming_data.copy()
                mutable["answers"] = reconstructed
                incoming_data = mutable
                answers_value = reconstructed

        # As a final fallback, try reconstructing from the underlying Django request.POST
        if (answers_value is None or not isinstance(answers_value, dict)) and hasattr(base_request, "POST"):
            reconstructed = {}
            for key, value in base_request.POST.items():
                if isinstance(key, str) and key.startswith("answers[") and key.endswith("]"):
                    qid = key[len("answers[") : -1]
                    reconstructed[qid] = value
            if reconstructed:
                incoming_data = {"answers": reconstructed}
                answers_value = reconstructed

        if isinstance(answers_value, str):
            try:
                decoded = json.loads(answers_value)
                # Rebuild mutable copy with decoded answers
                mutable = incoming_data.copy()
                mutable["answers"] = decoded
                incoming_data = mutable
            except Exception:
                # Leave as-is; serializer will surface a clear error
                pass

        serializer = SurveySubmissionSerializer(
            data=incoming_data,
            context={"survey": survey},
        )
        # Debug aid for tests: ensure payload shape is as expected
        # Remove or silence if noisy in production logs
        # print("incoming_data", incoming_data)
        serializer.is_valid(raise_exception=True)
        answers = serializer.validated_data["answers"]

        department = None
        if hasattr(request.user, "employee_profile"):
            department = request.get_own_profile(user).department

        response = SurveyResponse.objects.create(
            survey=survey,
            answers=answers,
            department=department,
        )

        return self.success_response(
            {
                "detail": "Survey submitted successfully.",
                "response_id": str(response.response_id),
            },
            status=status.HTTP_201_CREATED,
        )


class SurveyStatsView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, survey_id):
        user = request.user
        if not (has_hr_access(user) or is_auditor(user)):
            raise PermissionDenied("Only HR, Admin, or Auditors can view global wellbeing stats.")

        survey = get_object_or_404(WellbeingSurvey, pk=survey_id)
        responses = SurveyResponse.objects.filter(survey=survey)

        questions_data = []
        for q in survey.questions.all():
            qid = str(q.id)
            q_data = {"id": q.id, "text": q.text, "type": q.type}

            values = [r.answers.get(qid) for r in responses if qid in r.answers]

            if q.type == SurveyQuestion.QuestionType.SCALE_1_5:
                nums = []
                dist = {str(i): 0 for i in range(1, 6)}
                for v in values:
                    try:
                        n = int(v)
                        if 1 <= n <= 5:
                            nums.append(n)
                            dist[str(n)] += 1
                    except Exception:
                        continue
                q_data["avg"] = sum(nums) / len(nums) if nums else None
                q_data["distribution"] = dist

            elif q.type == SurveyQuestion.QuestionType.YES_NO:
                yes = sum(str(v).lower() in ["yes", "oui"] for v in values)
                no = sum(str(v).lower() in ["no", "non"] for v in values)
                q_data["yes"] = yes
                q_data["no"] = no

            else:  # TEXT
                q_data["count_text"] = len(values)

            questions_data.append(q_data)

        payload = {
            "count_responses": responses.count(),
            "questions": questions_data,
        }

        s = SurveyStatsSerializer(data=payload)
        s.is_valid(raise_exception=True)

        return self.success_response(s.data)


class TeamStatsView(ApiResponseMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, survey_id):
        user = request.user
        survey = get_object_or_404(WellbeingSurvey, pk=survey_id)

        # Team filtering
        if has_hr_access(user) or is_auditor(user):
            team_profiles = EmployeeProfile.objects.all()
        elif is_manager(user) and get_own_profile(user) is not None:
            team_profiles = EmployeeProfile.objects.filter(manager=get_own_profile(user))
        else:
            raise PermissionDenied("Only managers, HR/Admin, or Auditors can view team stats.")

        team_size = team_profiles.count()
        dept_ids = {p.department_id for p in team_profiles if p.department_id}

        if not dept_ids:
            return self.success_response(
                {"team_size": team_size, "responses": 0, "aggregates": {}}
            )

        responses = SurveyResponse.objects.filter(
            survey=survey,
            department_id__in=dept_ids,
        )

        # Aggregates
        aggregates = {}
        for q in survey.questions.all():
            if q.type != SurveyQuestion.QuestionType.SCALE_1_5:
                continue
            qid = str(q.id)
            nums = []
            for r in responses:
                if qid in r.answers:
                    try:
                        n = int(r.answers[qid])
                        if 1 <= n <= 5:
                            nums.append(n)
                    except Exception:
                        continue
            aggregates[qid] = sum(nums) / len(nums) if nums else None

        payload = {
            "team_size": team_size,
            "responses": responses.count(),
            "aggregates": aggregates,
        }

        s = TeamStatsSerializer(data=payload)
        s.is_valid(raise_exception=True)

        return self.success_response(s.data)
