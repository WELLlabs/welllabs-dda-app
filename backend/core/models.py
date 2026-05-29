from django.contrib.gis.db import models

# Create your models here.

from django.contrib.gis.db import models


class Watershed(models.Model):
    fid = models.AutoField(primary_key=True)

    id = models.CharField(max_length=255, null=True, blank=True)

    dn = models.IntegerField(null=True, blank=True)

    uid = models.CharField(max_length=255, null=True, blank=True)

    geom = models.MultiPolygonField()

    class Meta:
        managed = True
        db_table = 'watersheds'
