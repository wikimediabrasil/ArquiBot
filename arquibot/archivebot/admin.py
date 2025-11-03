from django.contrib import admin
from archivebot.models import Wikipedia
from archivebot.models import ArticleCheck
from archivebot.models import UrlCheck


@admin.register(Wikipedia)
class WikipediaAdmin(admin.ModelAdmin):
    list_display = ("code",)


@admin.register(ArticleCheck)
class ArticleCheckAdmin(admin.ModelAdmin):
    search_fields = ["title"]
    list_filter = ["wikipedia", "modified"]
    list_display = [
        "wikipedia",
        "title",
        "edit_id",
        "modified",
    ]
    list_select_related = ["wikipedia"]


@admin.register(UrlCheck)
class UrlCheckAdmin(admin.ModelAdmin):
    search_fields = ["article__title", "url"]
    list_filter = ["status", "is_url_dead", "modified"]
    list_display = [
        "article",
        "url",
        "status",
        "archive_url",
        "is_url_dead",
        "modified",
    ]
    list_select_related = ["article__wikipedia"]
