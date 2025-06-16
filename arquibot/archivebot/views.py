from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import BotRunStats
from .serializers import BotRunStatsSerializer

@api_view(['GET'])
def stats_api_view(request):
    stats = BotRunStats.objects.order_by('-run_date')[:30]
    serializer = BotRunStatsSerializer(stats, many=True)
    return Response(serializer.data)

def stats_page(request):
    return render(request, 'archivebot/stats.html')

