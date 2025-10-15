from django.db import models

class BotRunStats(models.Model):
    run_date = models.DateTimeField(auto_now_add=True)
    articles_scanned = models.IntegerField()
    urls_checked = models.IntegerField()
    urls_archived = models.IntegerField()
    edits_made = models.IntegerField()

    def __str__(self):
        return f"Bot run on {self.run_date.strftime('%Y-%m-%d %H:%M')}"

class ArchivedCitation(models.Model):
    article_title = models.CharField(max_length=255)
    original_template = models.TextField()
    updated_template = models.TextField()
    url = models.URLField()
    arquivourl = models.URLField(blank=True, null=True)
    arquivodata = models.DateField(blank=True, null=True)
    urlmorta = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.article_title} - {self.url}"
