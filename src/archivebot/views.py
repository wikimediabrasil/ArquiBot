from datetime import datetime
from datetime import time

from django.shortcuts import render
from django.utils import timezone
from django.utils.timezone import now

from archivebot.models import UrlCheck
from archivebot.models import Wikipedia
from stats.models import Statistics
from stats.models import Timestamp


def home(request):
    wikipedias = Wikipedia.objects.exclude(code="test").all()
    data = {
        "wikipedias": wikipedias,
    }
    return render(request, "home.html", data)


def stats(request):
    request_date = request.GET.get("date")
    date = None
    if request_date:
        date = datetime.strptime(request_date, "%Y-%m-%d")
        timestamp = Timestamp.objects.of_date(date)
    else:
        timestamp = Timestamp.objects.order_by("-datetime").first()
        if timestamp:
            date = timestamp.date

    statistics = Statistics.objects.of_timestamp(timestamp)
    data = {
        "timestamp": timestamp,
        "statistics": statistics,
        "date_fmt": date.strftime("%Y-%m-%d") if date else None,
    }
    status = 404 if timestamp is None else 200
    return render(request, "stats.html", data, status=status)


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
