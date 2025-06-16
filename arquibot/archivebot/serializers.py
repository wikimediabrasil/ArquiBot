from rest_framework import serializers
from .models import BotRunStats

class BotRunStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotRunStats
        fields = '__all__'

