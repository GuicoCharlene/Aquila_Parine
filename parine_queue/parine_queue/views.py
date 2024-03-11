from django.contrib import messages
from django.shortcuts import render, redirect
from .models import QueueVisitor, QueueEntry, Kiosk
import pymysql
from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count
    
def landing(request):
    return render(request, 'landing.html')

def homepage(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            # Establishing connection to the database
            conn = pymysql.connect(
                host='localhost',
                user='root',
                password='Cg_09355975720',
                database='parine'
            )
            cursor = conn.cursor()
            query = "SELECT username, pwd, reserve FROM visitor WHERE username = %s AND password = %s"
            cursor.execute(query, (username, password))
            row = cursor.fetchone()

            if row:
                username, pwd, reserve = row
                
                # Determining priority based on pwd and reserve values
                if pwd:
                    priority = "high"
                elif reserve:
                    priority = "mid"
                else:
                    priority = "low"
                
                # Creating or fetching the QueueVisitor instance
                user, created = QueueVisitor.objects.get_or_create(username=username, defaults={'pwd': pwd, 'reserve': reserve})

                
                queue_entry, queue_created = QueueEntry.objects.get_or_create(user=user, defaults={'PriorityLevel': priority})
                
                if queue_created:
                    messages.success(request, 'You have been successfully added to the queue.')
                else:
                    messages.info(request, 'You are already in the queue.')
                
                return redirect('queue')
            
            else:
                messages.error(request, 'Invalid username or password')
                return redirect('homepage')
        except Exception as e:
            error_message = f'An error occurred while processing your request: {str(e)}'
            messages.error(request, error_message)
            return redirect('homepage')
    else:
        return render(request, 'homepage.html')

def queue(request):
    return render(request, 'queue.html')

def queue_list(request):
    view_list = True  # Always show the queue list
    if view_list:
        # Fetch all QueueEntry records, including related QueueVisitor records, and order by start_time
        queue_entries = QueueEntry.objects.all().select_related('user').order_by('PriorityLevel')
        
        # Check for inactive users and remove them from the queue
        for entry in queue_entries:
            if entry.StartTime and timezone.now() - entry.EndTime > timezone.timedelta(minutes=5):
                entry.delete()  # Remove inactive user from the queue
    
    else:
        queue_entries = []
        
    # Get total number of kiosks
    total_kiosks = Kiosk.objects.aggregate(total=Count('KioskID'))['total']
    
    data = Kiosk.objects.all()
    
    return render(request, 'queue_list.html', {'queue_entries': queue_entries, 'view_list': view_list, 'data': data, 'total_kiosks': range(total_kiosks)})