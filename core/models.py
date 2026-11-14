from django.db import models


class Family(models.Model):
    name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=64, default="Europe/Paris")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "families"

    def __str__(self):
        return self.name
