from unittest.util import _MAX_LENGTH
from django.db import models
from django.utils import timezone

class QueueVisitor(models.Model):
    username = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=255, unique=True)
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
    StartTime = models.DateTimeField(null=True, blank=True)  # Track the start time when user enters the kiosk
    EndTime = models.DateTimeField(null=True, blank=True)  # Track the end time when user exits the kiosk
    
    class Meta:
        db_table = 'queue'
    
class Kiosk(models.Model):
    KioskID = models.AutoField(primary_key=True)
    KioskStatus = models.BooleanField(default=False)
    TimeDuration = models.DateTimeField(null=True, blank=True)  
    QueueID = models.ForeignKey(QueueEntry, on_delete=models.CASCADE, db_column='QueueID(Q)')
    class Meta:
        db_table = 'kiosk'

class Admin(models.Model):
    AdminID = models.AutoField(primary_key=True)
    username = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=255, unique=True)  # Add password field for admin
    class Meta:
        db_table = 'admin'
        
class Queue_Capacity(models.Model):
    queue_capacity_id = models.IntegerField(primary_key=True)
    limit = models.IntegerField()
    class Meta:
        db_table = 'queue_capacity'
        
class DistrictModules(models.Model):
    DistrictModuleID = models.AutoField(primary_key=True)
    ModuleName = models.CharField(max_length=100)
    ModuleContent = models.FileField(upload_to='module_content/')  # store files in 'media/module_content/'
    ModuleFile = models.TextField()  # Use TextField for longtext
    KioskID = models.ForeignKey('Kiosk', on_delete=models.CASCADE, db_column='KioskID')
    AdminID = models.ForeignKey('Admin', on_delete=models.CASCADE, db_column='AdminID(DM)')

    class Meta:
        db_table = 'districtmodule'