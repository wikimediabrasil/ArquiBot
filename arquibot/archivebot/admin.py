from django.contrib import admin
from django.utils.html import format_html
from .models import ArchiveLog, BotRunStats, ArchivedCitation

@admin.register(ArchiveLog)
class ArchiveLogAdmin(admin.ModelAdmin):
    list_display = ('article_title', 'original_url_link', 'status', 'archived_url_link', 'timestamp')
    list_filter = ('status', 'timestamp')
    search_fields = ('article_title', 'url')

    def original_url_link(self, obj):
        return format_html('<a href="{}" target="_blank">Original</a>', obj.url)
    original_url_link.short_description = 'Original URL'

    def archived_url_link(self, obj):
        if obj.status == 'archived' and obj.message.startswith('http'):
            return format_html('<a href="{}" target="_blank">Archive</a>', obj.message)
        return "-"
    archived_url_link.short_description = 'Archived URL'

@admin.register(BotRunStats)
class BotRunStatsAdmin(admin.ModelAdmin):
    list_display = ('run_date', 'articles_scanned', 'urls_checked', 'urls_archived', 'edits_made')
    list_filter = ('run_date',)

@admin.register(ArchivedCitation)
class ArchivedCitationAdmin(admin.ModelAdmin):
    search_fields = ['article_title', 'url']
    list_filter = ['urlmorta', 'timestamp']
    list_display = ['article_title', 'url', 'urlmorta', 'arquivourl', 'arquivodata', 'timestamp']
