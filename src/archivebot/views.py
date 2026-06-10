from datetime import datetime
from datetime import time

from django.shortcuts import render
from django.utils import timezone
from django.utils.timezone import now

from archivebot.models import UrlCheck
from stats.models import Statistics
from stats.models import Timestamp


def _stats_data(timestamp):
    statistics = (
        Statistics.objects.filter(timestamp=timestamp)
        .exclude(edits=0)
        .exclude(wikipedia__code="test")
    )
    return {
        "statistics": statistics,
        "timestamp": timestamp,
    }


def home(request):
    data = {}
    timestamp = Timestamp.objects.order_by("-datetime").first()
    if timestamp:
        data = _stats_data(timestamp)
    return render(request, "stats.html", data)


def stats(request, id):
    timestamp = Timestamp.objects.get(id=id)
    data = _stats_data(timestamp)
    return render(request, "stats.html", data)


def logs(request):
    request_date = request.GET.get("date")
    if request_date:
        date = datetime.strptime(request_date, "%Y-%m-%d")
    else:
        date = now().date()

    start = timezone.make_aware(datetime.combine(date, time.min))
    end = timezone.make_aware(datetime.combine(date, time.max))

    urls = (
        UrlCheck.objects.filter(created__gte=start, created__lte=end)
        .select_related("article__wikipedia")
        .order_by("-modified")
    )

    data = {
        "date": date,
        "date_fmt": date.strftime("%Y-%m-%d"),
        "urls": urls,
    }

    return render(request, "logs.html", data)
