"""Serializers describing the HR-Open payloads for OpenAPI (drf-spectacular).

These are documentation/shape serializers: the actual payloads are produced by
``hr.interop.mappers``. Keeping them here gives Swagger/Redoc an accurate
contract without coupling the mappers to DRF.
"""

from rest_framework import serializers


class _TaxonomySerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class CompetencyDefinitionSerializer(serializers.Serializer):
    type = serializers.CharField(default="CompetencyDefinition")
    id = serializers.CharField(help_text="Skill code (stable competency id).")
    competencyId = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    competencyCategory = serializers.CharField()
    active = serializers.BooleanField()
    taxonomyId = serializers.CharField()
    taxonomy = _TaxonomySerializer()


class _ScoreSerializer(serializers.Serializer):
    value = serializers.IntegerField()
    maximumValue = serializers.IntegerField()
    name = serializers.CharField()
    scaleId = serializers.CharField()


class CompetencyDimensionSerializer(serializers.Serializer):
    type = serializers.CharField(default="CompetencyDimension")
    dimensionType = serializers.CharField(default="proficiency")
    score = _ScoreSerializer()
    targetValue = serializers.IntegerField(allow_null=True)
    targetGap = serializers.IntegerField(allow_null=True)


class CompetencyEvidenceSerializer(serializers.Serializer):
    type = serializers.CharField(default="CompetencyEvidence")
    typeId = serializers.CharField(default="assessment")
    name = serializers.CharField()
    assessedBy = serializers.IntegerField(allow_null=True)
    assessmentDate = serializers.DateTimeField(allow_null=True)
    note = serializers.CharField(allow_blank=True)


class _EffectiveDateRangeSerializer(serializers.Serializer):
    startDate = serializers.DateTimeField(allow_null=True)
    endDate = serializers.DateTimeField(allow_null=True)


class _PersonSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    employeeId = serializers.CharField(allow_null=True)
    sourceSystem = serializers.CharField(allow_null=True)
    name = serializers.CharField()
    departmentCode = serializers.CharField(allow_null=True)
    jobTitle = serializers.CharField(allow_null=True)


class _CompetencyRefSerializer(serializers.Serializer):
    id = serializers.CharField()
    competencyId = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()


class PersonCompetencySerializer(serializers.Serializer):
    type = serializers.CharField(default="PersonCompetency")
    id = serializers.CharField()
    person = _PersonSerializer()
    competency = _CompetencyRefSerializer()
    competencyDimensions = CompetencyDimensionSerializer(many=True)
    competencyEvidence = CompetencyEvidenceSerializer(many=True)
    effectiveDateRange = _EffectiveDateRangeSerializer()


class PositionCompetencyModelSerializer(serializers.Serializer):
    type = serializers.CharField(default="PositionCompetencyModel")
    id = serializers.CharField()
    orgUnit = serializers.DictField()
    headcount = serializers.IntegerField()
    proficiencyScale = serializers.DictField()
    competencies = serializers.ListField(child=serializers.DictField())
