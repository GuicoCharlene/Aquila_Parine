from django.contrib import messages
from django.shortcuts import render, redirect
from .models import QueueVisitor, QueueEntry
import pymysql

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
            query = "SELECT username, PWD, reserve FROM visitor WHERE username = %s AND password = %s"
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
                user, created = QueueVisitor.objects.get_or_create(username=username, defaults={'PWD': pwd, 'reserve': reserve})

                
                # Adding the user to the queue with their priority
                # Assuming 'priority' in QueueEntry should be a CharField to accommodate 'high', 'mid', 'low' values
                queue_entry, queue_created = QueueEntry.objects.get_or_create(user=user, defaults={'prioritylevel': priority})
                
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
        return render(request, 'parine_queue/homepage.html')


def queue(request):
    view_list = request.GET.get('viewlist', 'false').lower() == 'true'
    queue_entries = QueueEntry.objects.all().select_related('user').order_by('prioritylevel') if view_list else []
    
    return render(request, 'queue.html', {'queue_entries': queue_entries, 'view_list': view_list})
        

