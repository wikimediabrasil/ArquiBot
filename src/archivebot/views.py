from datetime import datetime
from datetime import time

from django.shortcuts import render
from django.utils import timezone
from django.utils.timezone import now

from archivebot.models import UrlCheck


def stats_page(request):
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

    return render(request, "archivebot/stats.html", data)
