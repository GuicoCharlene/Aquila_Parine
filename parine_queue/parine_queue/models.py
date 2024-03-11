from django.db import models
from django.utils import timezone


class QueueVisitor(models.Model):
    username = models.CharField(max_length=255, unique=True)
    pwd = models.BooleanField(default=False)
    reserve = models.BooleanField(default=False) 
    age = models.IntegerField(null=True, blank=True)
    VisitorID = models.AutoField(primary_key=True)

    class Meta:
        db_table = 'visitor'

class QueueEntry(models.Model):
    QueueID = models.AutoField(primary_key=True)
    user = models.ForeignKey(QueueVisitor, on_delete=models.CASCADE, db_column='VisitorID(Q)')
    PriorityLevel = models.CharField(max_length=10)
    QueueStatus = models.CharField(max_length=45)
    QueueLimit = models.CharField(max_length=45)
    StartTime = models.DateTimeField(default=timezone.now)
    EndTime = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'queue'
    
class Kiosk(models.Model):
    KioskID = models.AutoField(primary_key=True)  # Corrected primary key definition
    KioskStatus = models.BooleanField(default=False)
    TimeDuration = models.DateTimeField()
    
    class Meta:
        db_table = 'kiosk'
