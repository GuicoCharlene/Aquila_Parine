# In tasks.py
from celery import shared_task
from django.utils import timezone
from .models import QueueEntry

@shared_task
def delete_old_queue_entries():
    # Calculate the threshold time (5 minutes ago)
    threshold_time = timezone.now() - timezone.timedelta(minutes=5)
    
    # Query and delete queue entries older than the threshold time
    QueueEntry.objects.filter(StartTime__lt=threshold_time, QueueStatus='PENDING').delete()
