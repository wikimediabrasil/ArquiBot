from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import ArchiveLog, BotRunStats

@admin.register(ArchiveLog)
class ArchiveLogAdmin(admin.ModelAdmin):
    list_display = ('article_title', 'url', 'status', 'timestamp')
    list_filter = ('status', 'timestamp')
    search_fields = ('article_title', 'url')

@admin.register(BotRunStats)
class BotRunStatsAdmin(admin.ModelAdmin):
    list_display = ('run_date', 'articles_scanned', 'urls_checked', 'urls_archived', 'edits_made')
    list_filter = ('run_date',)
