from django.db import models
from django.utils import timezone

class QueueVisitor(models.Model):
    username = models.CharField(max_length=255, unique=True)  # Add this line
    PWD = models.BooleanField(default=False)
    reserve = models.BooleanField(default=False)  # Assuming you add this based on previous discussions
    age = models.IntegerField(null=True, blank=True)
    VisitorID = models.AutoField(primary_key=True)

    class Meta:
        db_table = 'visitor'

class QueueEntry(models.Model):
    # user = models.ForeignKey(QueueVisitor, on_delete=models.CASCADE)
    QueueID = models.AutoField(primary_key=True)
    user = models.ForeignKey(QueueVisitor, on_delete=models.CASCADE, db_column='VisitorID')
    prioritylevel = models.CharField(max_length=10)
    queue_status = models.CharField(max_length=45)
    queue_limit = models.CharField(max_length=45)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(default=timezone.now)


    class Meta:
        db_table = 'queue'
