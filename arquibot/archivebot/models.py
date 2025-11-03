from django.db import models
from django.conf import settings
from django.utils.translation import pgettext_lazy


class Wikipedia(models.Model):
    code = models.CharField(max_length=32, help_text="'pt', 'test', etc")

    def __str__(self):
        return self.code + " wikipedia"

    @staticmethod
    def get() -> "Wikipedia":
        wikipedia, _ = Wikipedia.objects.get_or_create(code=settings.WIKIPEDIA_CODE)
        return wikipedia

    def url(self):
        return f"https://{self.code}.wikipedia.org"

    def action_api(self):
        return self.url() + "/w/api.php"

    def rest_api(self):
        return self.url() + "/w/rest.php/v1"


class ArticleCheck(models.Model):
    wikipedia = models.ForeignKey(Wikipedia, on_delete=models.CASCADE)
    title = models.CharField(max_length=256)
    edit_id = models.PositiveIntegerField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def url(self):
        return self.wikipedia.url() + "/wiki/" + self.title

    def edit_url(self):
        if self.edit_id:
            return f"{self.wikipedia.url()}/w/index.php?title={self.title}&diff=prev&oldid={self.edit_id}"


class UrlCheck(models.Model):
    article = models.ForeignKey(ArticleCheck, on_delete=models.CASCADE, related_name="urls")
    url = models.URLField()

    class ArchiveStatus(models.TextChoices):
        RUNNING = (
            "running",
            pgettext_lazy("url-status-running", "check running"),
        )
        ARCHIVED = (
            "archived",
            pgettext_lazy("url-status-archived", "successful archive"),
        )
        FAILED = (
            "failed",
            pgettext_lazy("url-status-failed", "archive failed"),
        )
        IGNORED_PERMALINK = (
            "ignored_permalink",
            pgettext_lazy("url-status-ignored-permalink", "Permalink ignored"),
        )
        IGNORED_ARCHIVED = (
            "ignored_archived",
            pgettext_lazy("url-status-ignored-archived", "URL already archived"),
        )

    status = models.CharField(
        max_length=32,
        blank=True,
        choices=ArchiveStatus.choices,
        default=ArchiveStatus.RUNNING,
    )
    archive_url = models.URLField(blank=True, null=True)
    is_url_dead = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def set_ignored_permalink(self):
        self.status = self.ArchiveStatus.IGNORED_PERMALINK
        self.save()

    def set_ignored_archived(self):
        self.status = self.ArchiveStatus.IGNORED_ARCHIVED
        self.save()

    def set_failed(self, is_url_dead: bool):
        self.is_url_dead = is_url_dead
        self.status = self.ArchiveStatus.FAILED
        self.save()

    def set_archived(self, archive_url: str, is_url_dead: bool):
        self.archive_url = archive_url
        self.is_url_dead = is_url_dead
        self.status = self.ArchiveStatus.ARCHIVED
        self.save()
