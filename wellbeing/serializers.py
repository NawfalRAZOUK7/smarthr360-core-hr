# wellbeing/serializers.py
from rest_framework import serializers

from .models import SurveyQuestion, WellbeingSurvey


class SurveyQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyQuestion
        fields = [
            "id",
            "text",
            "type",
            "order",
            "created_at",
        ]
        read_only_fields = ["created_at"]

class WellbeingSurveySerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = WellbeingSurvey
        fields = [
            "id",
            "title",
            "description",
            "is_active",
            "created_by_user_id",
            "created_at",
            "updated_at",
            "questions",
        ]
        read_only_fields = ["created_by_user_id", "created_at", "updated_at"]

class SurveySubmissionSerializer(serializers.Serializer):
    """
    Used for POST employee answers to:
    /api/wellbeing/surveys/<id>/submit/
    """

    answers = serializers.DictField(
        child=serializers.CharField(),
        help_text="Dictionary of {question_id: answer}"
    )

    def validate(self, data):
        survey = self.context.get("survey")
        answers = data.get("answers")

        # Ensure all question IDs exist
        question_ids = set(str(q.id) for q in survey.questions.all())
        provided_ids = set(answers.keys())

        missing = question_ids - provided_ids
        if missing:
            raise serializers.ValidationError(
                {"answers": f"Missing answers for questions: {', '.join(missing)}"}
            )

        # Type checking
        for q in survey.questions.all():
            qid = str(q.id)
            value = answers[qid]

            if q.type == SurveyQuestion.QuestionType.SCALE_1_5:
                try:
                    num = int(value)
                except ValueError:
                        raise serializers.ValidationError({qid: "Expected a number 1–5."}) from None
                if num < 1 or num > 5:
                    raise serializers.ValidationError(
                        {qid: "Scale answer must be between 1 and 5."}
                    )

            elif q.type == SurveyQuestion.QuestionType.YES_NO:
                if value.lower() not in ["yes", "no", "oui", "non"]:
                    raise serializers.ValidationError(
                        {qid: "Expected yes/no."}
                    )

            # TEXT → anything is accepted

        return data

class SurveyStatsSerializer(serializers.Serializer):
    """
    Returned for:
    GET /api/wellbeing/surveys/<id>/stats/
    """

    count_responses = serializers.IntegerField()
    questions = serializers.ListField()

class TeamStatsSerializer(serializers.Serializer):
    team_size = serializers.IntegerField()
    responses = serializers.IntegerField()

    # dynamic questions → simplified values
    aggregates = serializers.DictField()
