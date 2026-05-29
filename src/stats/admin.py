from django.contrib import admin

from .models import Statistics

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
