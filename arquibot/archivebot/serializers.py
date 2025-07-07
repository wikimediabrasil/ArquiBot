from rest_framework import serializers
from .models import ArchiveLog, BotRunStats, ArchivedCitation

class ArchiveLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchiveLog
        fields = ['id', 'url', 'article_title', 'status', 'message', 'timestamp']

class BotRunStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotRunStats
        fields = '__all__'

class ArchivedCitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchivedCitation
        fields = '__all__'