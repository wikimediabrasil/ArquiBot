from django.db import models

# Create your models here.

class BotRunStats(models.Model):
    run_date = models.DateTimeField(auto_now_add=True)
    articles_scanned = models.IntegerField()
    urls_checked = models.IntegerField()
    urls_archived = models.IntegerField()
    edits_made = models.IntegerField()

    def __str__(self):
        return f"Bot run on {self.run_date.strftime('%Y-%m-%d %H:%M')}"
