from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Count
from django.utils.timezone import now, timedelta
from collections import defaultdict
from datetime import datetime
from .models import ArchiveLog, BotRunStats
from .serializers import ArchiveLogSerializer, BotRunStatsSerializer

@api_view(['GET'])
def combined_stats_api(request):
    # Summary Stats (BotRunStats)
    stats = BotRunStats.objects.order_by('-run_date')[:30]
    stats_data = BotRunStatsSerializer(stats, many=True).data

    # Recent Logs (ArchiveLog)
    logs = ArchiveLog.objects.order_by('-timestamp')[:100]
    logs_data = ArchiveLogSerializer(logs, many=True).data

    return Response({
        "summary_stats": stats_data,
        "archive_logs": logs_data
    })

def stats_page(request):
    today = now().date()
    start_date = today - timedelta(days=6)  # last 7 days

    logs = ArchiveLog.objects.filter(timestamp__date__gte=start_date)

    # Group by date
    stats = defaultdict(lambda: {
        'articles': set(),
        'urls_checked': 0,
        'urls_archived': 0,
        'edits_made': 0  # optional, you can decide how to define this
    })

    for log in logs:
        date_key = log.timestamp.date()
        stats[date_key]['articles'].add(log.article_title)
        stats[date_key]['urls_checked'] += 1
        if log.status == 'archived':
            stats[date_key]['urls_archived'] += 1
        # Optional: count each article scanned as an edit
        stats[date_key]['edits_made'] = len(stats[date_key]['articles'])

    # Convert sets to counts
    final_stats = []
    for date in sorted(stats.keys(), reverse=True):
        stat = stats[date]
        final_stats.append({
            'date': date.strftime("%Y-%m-%d"),
            'articles': len(stat['articles']),
            'urls_checked': stat['urls_checked'],
            'urls_archived': stat['urls_archived'],
            'edits_made': stat['edits_made'],
        })

    return render(request, 'archivebot/stats.html', {'stats': final_stats})
