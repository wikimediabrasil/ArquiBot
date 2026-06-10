from django.contrib import admin

from .models import Statistics
from .models import Timestamp


@admin.register(Statistics)
class StatisticsAdmin(admin.ModelAdmin):
    list_filter = ["wikipedia"]
    list_display = [
        "wikipedia",
        "edits",
        "urls_archived",
        "timestamp",
    ]
    list_select_related = ["wikipedia"]


class StatisticsInline(admin.TabularInline):
    model = Statistics
    extra = 0
    fields = ["wikipedia", "edits", "urls_archived"]


@admin.register(Timestamp)
class TimestampAdmin(admin.ModelAdmin):
    list_filter = ["datetime"]
    list_display = [
        "datetime",
    ]
    inlines = [StatisticsInline]
