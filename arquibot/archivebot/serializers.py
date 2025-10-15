from rest_framework import serializers
from .models import BotRunStats, ArchivedCitation

class BotRunStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotRunStats
        fields = '__all__'

class ArchivedCitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchivedCitation
        fields = '__all__'
