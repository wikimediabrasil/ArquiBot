from django.contrib import admin
from .models import BotRunStats, ArchivedCitation


@admin.register(BotRunStats)
class BotRunStatsAdmin(admin.ModelAdmin):
    list_display = ('run_date', 'articles_scanned', 'urls_checked', 'urls_archived', 'edits_made')
    list_filter = ('run_date',)

@admin.register(ArchivedCitation)
class ArchivedCitationAdmin(admin.ModelAdmin):
    search_fields = ['article_title', 'url']
    list_filter = ['urlmorta', 'timestamp']
    list_display = ['article_title', 'url', 'urlmorta', 'arquivourl', 'timestamp']
