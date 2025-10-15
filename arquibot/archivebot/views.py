from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils.timezone import now, timedelta
from collections import defaultdict
from .models import BotRunStats, ArchivedCitation
from .serializers import BotRunStatsSerializer, ArchivedCitationSerializer
from rest_framework import generics


@api_view(['GET'])
def combined_stats_api(request):
    # Summary Stats (BotRunStats)
    stats = BotRunStats.objects.order_by('-run_date')[:30]
    stats_data = BotRunStatsSerializer(stats, many=True).data

    # Recent Logs (ArchivedCitation)
    logs = ArchivedCitation.objects.order_by('-timestamp')[:100]
    logs_data = ArchivedCitationSerializer(logs, many=True).data

    return Response({
        "summary_stats": stats_data,
        "archive_logs": logs_data
    })

def stats_page(request):
    today = now().date()
    start_date = today - timedelta(days=6)

    logs = ArchivedCitation.objects.filter(timestamp__date__gte=start_date)
    stats = defaultdict(lambda: {
        'articles': set(),
        'urls_checked': 0,
        'urls_archived': 0,
    })

    for log in logs:
        date_key = log.timestamp.date()
        stats[date_key]['articles'].add(log.article_title)
        stats[date_key]['urls_checked'] += 1
        stats[date_key]['urls_archived'] += 1

    # Pull accurate edits_made from BotRunStats model
    stats_model_qs = BotRunStats.objects.filter(run_date__date__gte=start_date)
    edits_by_date = {s.run_date.date(): s.edits_made for s in stats_model_qs}

    # Build final list
    final_stats = []
    for date in sorted(stats.keys(), reverse=True):
        stat = stats[date]
        final_stats.append({
            'date': date.strftime("%Y-%m-%d"),
            'articles': len(stat['articles']),
            'urls_checked': stat['urls_checked'],
            'urls_archived': stat['urls_archived'],
            'edits_made': edits_by_date.get(date, 0), 
        })

    return render(request, 'archivebot/stats.html', {'stats': final_stats})

class ArchivedCitationList(generics.ListAPIView):
    queryset = ArchivedCitation.objects.all().order_by('-timestamp')
    serializer_class = ArchivedCitationSerializer
