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
    StartTime = models.DateTimeField(null=True, blank=True)
    EndTime = models.DateTimeField(null=True, blank=True)
    
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
    password = models.CharField(max_length=255, unique=True)  
    class Meta:
        db_table = 'admin'
        
class Queue_Capacity(models.Model):
    queue_capacity_id = models.IntegerField(primary_key=True)
    limit = models.IntegerField()
    class Meta:
        db_table = 'queue_capacity'
        
class DistrictModules(models.Model):
    DistrictModuleID = models.CharField(primary_key=True, max_length=10)
    Municipality = models.CharField(max_length=100)
    ModuleName = models.CharField(max_length=100)
    ModuleLocation = models.CharField(max_length=100)
    ModuleContent = models.FileField(upload_to='module_content/')
    FirstImage = models.FileField(upload_to='module_content/')
    SecondImage = models.FileField(upload_to='module_content/')
    ThirdImage = models.FileField(upload_to='module_content/')
    ModuleFile = models.TextField()  # Use TextField for longtext
    KioskID = models.ForeignKey('Kiosk', on_delete=models.CASCADE, db_column='KioskID')
    AdminID = models.ForeignKey('Admin', on_delete=models.CASCADE, db_column='AdminID(DM)')

    class Meta:
        db_table = 'districtmodule'
        
class TriviaQuestion(models.Model):
    TriviaQuestionID = models.AutoField(primary_key=True)
    Municipality = models.CharField(max_length=100)
    ModuleType = models.CharField(max_length=100)
    Images =models.FileField(upload_to='module_content/')
    QuestionContent = models.TextField() #HOLDS THE QUESTION
    QuestionAnswer = models.TextField() #HOLDS THE ANSWER
    DistrictModuleID = models.ForeignKey('Kiosk', on_delete=models.CASCADE, db_column='DistrictModuleID(TQ)')
    AdminID = models.ForeignKey('Admin', on_delete=models.CASCADE, db_column='AdminID(TQ)')

    class Meta:
        db_table = 'triviaquestion'
        
class RewardPoints(models.Model):
    RewardPointsID = models.AutoField(primary_key=True)
    TotalPoints =  models.IntegerField(default=0)
    create_time = models.DateTimeField(null=True, blank=True)
    update_time = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(QueueVisitor, on_delete=models.CASCADE, db_column='VisitorID(RP)')
    Municipality = models.CharField(max_length=100)
    ModuleType = models.CharField(max_length=100)
    TriviaQuestionID = models.ForeignKey(TriviaQuestion, on_delete=models.CASCADE, db_column='TriviaQuestionID', null=True, blank=True)

    class Meta:
        db_table = 'rewardpoints'
        
class Visitor_History(models.Model):
    historyid = models.AutoField(primary_key=True)
    date = models.DateField(null=True, blank=True)  # Changed to DateField
    user = models.CharField(max_length=255, unique=True)
    userid = models.ForeignKey(QueueVisitor, on_delete=models.CASCADE, db_column='VisitorID(Q)')
    class Meta:
        db_table = 'visitorhistory'
        
class VisitorProgress(models.Model):
    VisitorProgressID = models.AutoField(primary_key=True)
    VisitorID = models.ForeignKey(QueueVisitor, on_delete=models.CASCADE, db_column='VisitorID')
    Municipality = models.CharField(max_length=100)
    ModuleType = models.CharField(max_length=100)
    Status = models.CharField(max_length=100)
    class Meta:
        db_table = 'visitorprogress'
        
