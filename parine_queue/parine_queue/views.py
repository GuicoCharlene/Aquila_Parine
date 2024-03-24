from django.contrib import messages
from django.shortcuts import render, redirect
from .models import QueueVisitor, QueueEntry, Kiosk, Admin, Queue_Capacity, DistrictModules, TriviaQuestion, RewardPoints
import random
from django.utils import timezone
from datetime import timedelta
from django.http import HttpResponseRedirect, JsonResponse
from .models import QueueEntry, Kiosk
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.http import HttpResponseBadRequest
import logging
from django.db import transaction
from django.urls import reverse
from django.db.models import F

logger = logging.getLogger(__name__)

# View for the landing page
def homepage(request):
    return render(request, 'homepage.html')

# View for that handles login
def login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        is_admin_login = request.POST.get('validate_only_admin') == 'on'  # Check if admin login

        if is_admin_login:
            request.session['logged_in_username'] = username
            # Admin login
            try:
                admin_user = Admin.objects.get(username=username, password=password)
                messages.success(request, 'Admin validated successfully.')
                return redirect('adminpage')  # Redirect to the admin page URL
            except Admin.DoesNotExist:
                messages.error(request, 'Invalid admin credentials')
                return redirect('login')
        else:
            try:
                # Check the total number of users in the queue
                total_users_in_queue = QueueEntry.objects.count()
                
                # Get the queue capacity limit
                queue_capacity_limit = Queue_Capacity.objects.values_list('limit', flat=True).first()
                
                # Check if the total users in the queue is less than the capacity limit
                if total_users_in_queue < queue_capacity_limit:
                    visitor = QueueVisitor.objects.get(username=username, password=password)
                    request.session['logged_in_username'] = username
                    
                    # Determining the priority level based on pwd and reserve values
                    priority = "high" if visitor.pwd else "mid" if visitor.reserve else "low"
                    
                    queue_entry, created = QueueEntry.objects.get_or_create(user=visitor, defaults={'PriorityLevel': priority, 'QueueStatus': 'WAITING', 'StartTime': timezone.now()})
                    
                    if created:
                        messages.success(request, 'You have been successfully added to the queue.')
                    else:
                        messages.info(request, 'You are already in the queue.')
                    
                    return redirect('queue')
                else:
                    messages.error(request, 'Queue is at full capacity. Please try again later.')
                    return redirect('login')
                
            except QueueVisitor.DoesNotExist:
                messages.error(request, 'Invalid username or password')
                return redirect('login')
    else:

        return render(request, 'login.html')

# View for displaying the queue page
def queue(request):
    return render(request, 'queue.html')

def queue_list(request):
    is_admin = request.session.get('is_admin', False)

    # Assign users from the queue to available kiosks
    for queue_entry in QueueEntry.objects.exclude(QueueStatus='IN KIOSK').exclude(QueueStatus='IN MODULE').exclude(QueueStatus='INACTIVE').select_related('user').order_by('PriorityLevel'):
        available_kiosk = Kiosk.objects.filter(KioskStatus=False).first()
        if available_kiosk:
            available_kiosk.KioskStatus = True
            available_kiosk.QueueID = queue_entry
            available_kiosk.TimeDuration = timezone.now()
            available_kiosk.save()
            # Update queue entry status and end time
            queue_entry.EndTime = timezone.now()  # Update EndTime to match current time
            if queue_entry.StartTime:
                time_spent = timezone.now() - queue_entry.StartTime
                hours = int(time_spent.total_seconds() // 3600)
                minutes = int((time_spent.total_seconds() % 3600) // 60)
                queue_entry.EndTime = queue_entry.StartTime + timedelta(hours=hours, minutes=minutes)
            # Update QueueStatus to 'IN KIOSK' only if it's not already 'IN MODULE' or 'INACTIVE'
            if queue_entry.QueueStatus != 'IN MODULE':
                queue_entry.QueueStatus = 'IN KIOSK'
                queue_entry.save()
                
            else: queue_entry.QueueStatus != 'INACTIVE'
            queue_entry.QueueStatus = 'IN KIOSK'
            queue_entry.save()
                

    # Check if the current user is assigned to a kiosk
    logged_in_username = request.session.get('logged_in_username')
    if logged_in_username:
        assigned_kiosk = Kiosk.objects.filter(QueueID__user__username=logged_in_username).first()
        

    # Prepare the data for displaying in the kiosk container
    kiosks_data = []
    for kiosk in Kiosk.objects.all():
        user = "AVAILABLE"
        start_time = "N/A"
        time_spent = "N/A"
        if kiosk.KioskStatus and kiosk.TimeDuration:
            start_time = kiosk.TimeDuration.strftime('%Y-%m-%dT%H:%M:%S')
            elapsed_time = timezone.now() - kiosk.TimeDuration
            time_spent = f"{int(elapsed_time.total_seconds() // 3600)}h {int((elapsed_time.total_seconds() // 60) % 60)}m"
            user = kiosk.QueueID.user.username if kiosk.QueueID and kiosk.QueueID.user else "N/A"
        kiosks_data.append({
            'KioskID': kiosk.KioskID,
            'user': user,
            'time_spent': time_spent,
            'start_time': start_time,
            'status': '0' if not kiosk.KioskStatus else '1'
        })

    context = {
        'queue_entries': QueueEntry.objects.exclude(QueueStatus='IN KIOSK').exclude(QueueStatus='IN MODULE').exclude(QueueStatus='INACTIVE').select_related('user').order_by('PriorityLevel'),
        'kiosks_data': kiosks_data,
        'is_admin': is_admin,
        'logged_in_username': logged_in_username,
    }

    return render(request, 'queue_list.html', context)

# View for the admin page
def adminpage(request):
    view_list = True  # Always show the queue list

    queue_capacity_value = Queue_Capacity.objects.values_list('limit', flat=True).first()
    if view_list:
        queue_entries = QueueEntry.objects.all().select_related('user').order_by('PriorityLevel')
    
    context = {
        'queue_entries': queue_entries,
        'view_list': view_list,
        'queue_capacity_value': queue_capacity_value,
    }
    return render(request, 'adminpage.html', context)

def update_queue_capacity(request):
    if request.method == 'POST':
        queue_capacity_value = request.POST.get('queue_capacity')
        if queue_capacity_value is None:
            # Redirect back to the admin page
            return HttpResponseRedirect('/adminpage')
        elif queue_capacity_value.strip() == "":
            # If the input is empty, redirect back to the admin page
            return HttpResponseRedirect('/adminpage')
        else:
            try:
                # Fetch the Queue_Capacity object with queue_capacity_id equals to 1
                queue_capacity = Queue_Capacity.objects.get(queue_capacity_id=1)
                
                # Update the queue capacity value
                queue_capacity.limit = queue_capacity_value
                queue_capacity.save()
                return redirect('adminpage')
            except Queue_Capacity.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Queue Capacity object with queue_capacity_id 1 does not exist'})
    return JsonResponse({'success': False, 'message': 'Invalid request method or missing queue_capacity value'})

# Views for the select district
def selectdistrict(request, kiosk_id):
    logged_in_username = request.session.get('logged_in_username')
    current_time = timezone.now()
    kiosk_username = None

    # Check and handle kiosks that have exceeded time limits
    for kiosk in Kiosk.objects.filter(KioskStatus=True).select_related('QueueID'):
        if kiosk.QueueID and kiosk.QueueID.EndTime:
            time_elapsed = current_time - kiosk.QueueID.EndTime
            if time_elapsed >= timedelta(minutes=2):
                queue_entry = kiosk.QueueID
                if queue_entry.QueueStatus == 'IN KIOSK':
                    kiosk.QueueID.delete()
                    kiosk.KioskStatus = False
                    kiosk.QueueID = None
                    kiosk.TimeDuration = None
                    kiosk.save()
        else:
            kiosk.KioskStatus = False
            kiosk.TimeDuration = None
            kiosk.save()

    try:
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        if kiosk.QueueID:
            kiosk_username = kiosk.QueueID.user.username
            if not kiosk.QueueID.QueueStatus == 'IN MODULE':
                kiosk.QueueID.QueueStatus = 'IN MODULE'
                
        if logged_in_username:
            queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
            if not kiosk.QueueID:
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = current_time
                kiosk.save()
                
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
    }
    return render(request, 'selectdistrict.html',context)

#THIS IS THE VIEW TO GET THE NEEDED DATA TO UPDATE THE TIME
def get_queue_data(request):
    try:
        kiosks = Kiosk.objects.all()
        kiosk_data = []
        for kiosk in kiosks:
            kiosk_info = {
                'KioskID': kiosk.KioskID,
                'user': None,
                'start_time': None,
            }
            
            if kiosk.QueueID_id and kiosk.QueueID.user:
                kiosk_info['user'] = kiosk.QueueID.user.username
                # Format start time if available
                if kiosk.TimeDuration:
                    kiosk_info['start_time'] = kiosk.TimeDuration.strftime('%Y-%m-%dT%H:%M:%S')

            # Append the info for this kiosk to the list
            kiosk_data.append(kiosk_info)

        return JsonResponse({'kiosk_data': kiosk_data})
    except Exception as e:
        logger.error(f"Error fetching kiosk data: {e}", exc_info=True)
        return JsonResponse({'error': 'Internal Server Error'}, status=500)


#user login in kiosk
def kiosk_login(request, kiosk_id):
    logged_in_username = request.session.get('logged_in_username')
    current_time = timezone.now()
    kiosk_username = None

    # Check and handle kiosks that have exceeded time limits
    for kiosk in Kiosk.objects.filter(KioskStatus=True).select_related('QueueID'):
        if kiosk.QueueID and kiosk.QueueID.EndTime:
            time_elapsed = current_time - kiosk.QueueID.EndTime
            if time_elapsed >= timedelta(minutes=1):
                queue_entry = kiosk.QueueID
                if queue_entry.QueueStatus == 'IN KIOSK':
                    kiosk.QueueID.delete()
                    kiosk.KioskStatus = False
                    kiosk.QueueID = None
                    kiosk.TimeDuration = None
                    kiosk.save()
        else:
            kiosk.KioskStatus = False
            kiosk.TimeDuration = None
            kiosk.save()

    try:
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        if kiosk.QueueID:
            kiosk_username = kiosk.QueueID.user.username
            if not kiosk.QueueID.QueueStatus == 'IN MODULE':
                kiosk.QueueID.QueueStatus = 'IN MODULE'
                kiosk.QueueID.save()
                
        if logged_in_username:
            queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
            if not kiosk.QueueID:
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = current_time
                kiosk.save()
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
    }

    return render(request, f'kiosk{kiosk_id}_login.html', context)

#Views for logout in kiosk
@transaction.atomic
def kiosk_logout(request, kiosk_id):
    try:
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)

        if kiosk.QueueID:
            kiosk.QueueID.delete()
            kiosk.QueueID = None
        
        # Reset kiosk status regardless of whether there was a QueueID
        kiosk.KioskStatus = False
        kiosk.TimeDuration = None
        kiosk.save()

    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")

    return render(request, 'kiosk_logout.html', {'kiosk_id': kiosk_id})

#TO DELETE INACTIVE USER BASED ON THE WAITING TIME LIMIT IN KIOSK
@csrf_exempt
def delete_queue_kiosk_data(request, kioskId):
    if request.method == 'POST':
        try:
            kiosk = Kiosk.objects.get(KioskID=kioskId)
            queue_entries = QueueEntry.objects.filter(QueueID=kiosk.QueueID_id)
            for entry in queue_entries:
                entry.user
                entry.QueueStatus = 'INACTIVE'
                entry.delete()  # This deletes the QueueEntry
                
            kiosk.KioskStatus = False  # RETURN TO THE AVAILABLE KIOSK STATUS
            kiosk.QueueID = None
            kiosk.TimeDuration = None
            kiosk.save()

            return JsonResponse({'status': 'success'}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def admin_district_1(request):
   
    return render(request, 'admin_district_1.html')

def admin_district_2(request):
   
    return render(request, 'admin_district_2.html')

def admin_district_3(request):
   
    return render(request, 'admin_district_3.html')

def admin_district_4(request):
   
    return render(request, 'admin_district_4.html')

def admin_district_5(request):
   
    return render(request, 'admin_district_5.html')

def admin_district_6(request):
   
    return render(request, 'admin_district_6.html')

def selectmunicipality1(request, kiosk_id):
    logged_in_username = request.session.get('logged_in_username')
    current_time = timezone.now()
    kiosk_username = None

    # Check and handle kiosks that have exceeded time limits
    for kiosk in Kiosk.objects.filter(KioskStatus=True).select_related('QueueID'):
        if kiosk.QueueID and kiosk.QueueID.EndTime:
            time_elapsed = current_time - kiosk.QueueID.EndTime
            if time_elapsed >= timedelta(minutes=1):
                queue_entry = kiosk.QueueID
                if queue_entry.QueueStatus == 'IN KIOSK':
                    kiosk.QueueID.delete()
                    kiosk.KioskStatus = False
                    kiosk.QueueID = None
                    kiosk.TimeDuration = None
                    kiosk.save()
        else:
            kiosk.KioskStatus = False
            kiosk.TimeDuration = None
            kiosk.save()

    try:
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        if kiosk.QueueID:
            kiosk_username = kiosk.QueueID.user.username
            if not kiosk.QueueID.QueueStatus == 'IN MODULE':
                kiosk.QueueID.QueueStatus = 'IN MODULE'
                kiosk.QueueID.save()
                
        if logged_in_username:
            queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
            if not kiosk.QueueID:
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = current_time
                kiosk.save()
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
    }

    return render(request, 'selectmunicipality1.html', context)

def selectmunicipality2(request, kiosk_id):
    logged_in_username = request.session.get('logged_in_username')
    current_time = timezone.now()
    kiosk_username = None

    # Check and handle kiosks that have exceeded time limits
    for kiosk in Kiosk.objects.filter(KioskStatus=True).select_related('QueueID'):
        if kiosk.QueueID and kiosk.QueueID.EndTime:
            time_elapsed = current_time - kiosk.QueueID.EndTime
            if time_elapsed >= timedelta(minutes=1):
                queue_entry = kiosk.QueueID
                if queue_entry.QueueStatus == 'IN KIOSK':
                    kiosk.QueueID.delete()
                    kiosk.KioskStatus = False
                    kiosk.QueueID = None
                    kiosk.TimeDuration = None
                    kiosk.save()
        else:
            kiosk.KioskStatus = False
            kiosk.TimeDuration = None
            kiosk.save()

    try:
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        if kiosk.QueueID:
            kiosk_username = kiosk.QueueID.user.username
            if not kiosk.QueueID.QueueStatus == 'IN MODULE':
                kiosk.QueueID.QueueStatus = 'IN MODULE'
                kiosk.QueueID.save()
                
        if logged_in_username:
            queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
            if not kiosk.QueueID:
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = current_time
                kiosk.save()
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
    }

    return render(request, 'selectmunicipality2.html', context)

def selectmunicipality3(request, kiosk_id):
    logged_in_username = request.session.get('logged_in_username')
    current_time = timezone.now()
    kiosk_username = None

    # Check and handle kiosks that have exceeded time limits
    for kiosk in Kiosk.objects.filter(KioskStatus=True).select_related('QueueID'):
        if kiosk.QueueID and kiosk.QueueID.EndTime:
            time_elapsed = current_time - kiosk.QueueID.EndTime
            if time_elapsed >= timedelta(minutes=1):
                queue_entry = kiosk.QueueID
                if queue_entry.QueueStatus == 'IN KIOSK':
                    kiosk.QueueID.delete()
                    kiosk.KioskStatus = False
                    kiosk.QueueID = None
                    kiosk.TimeDuration = None
                    kiosk.save()
        else:
            kiosk.KioskStatus = False
            kiosk.TimeDuration = None
            kiosk.save()

    try:
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        if kiosk.QueueID:
            kiosk_username = kiosk.QueueID.user.username
            if not kiosk.QueueID.QueueStatus == 'IN MODULE':
                kiosk.QueueID.QueueStatus = 'IN MODULE'
                kiosk.QueueID.save()
                
        if logged_in_username:
            queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
            if not kiosk.QueueID:
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = current_time
                kiosk.save()
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
    }

    return render(request, 'selectmunicipality3.html', context)

def selectmunicipality4(request, kiosk_id):
    logged_in_username = request.session.get('logged_in_username')
    current_time = timezone.now()
    kiosk_username = None

    # Check and handle kiosks that have exceeded time limits
    for kiosk in Kiosk.objects.filter(KioskStatus=True).select_related('QueueID'):
        if kiosk.QueueID and kiosk.QueueID.EndTime:
            time_elapsed = current_time - kiosk.QueueID.EndTime
            if time_elapsed >= timedelta(minutes=1):
                queue_entry = kiosk.QueueID
                if queue_entry.QueueStatus == 'IN KIOSK':
                    kiosk.QueueID.delete()
                    kiosk.KioskStatus = False
                    kiosk.QueueID = None
                    kiosk.TimeDuration = None
                    kiosk.save()
        else:
            kiosk.KioskStatus = False
            kiosk.TimeDuration = None
            kiosk.save()

    try:
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        if kiosk.QueueID:
            kiosk_username = kiosk.QueueID.user.username
            if not kiosk.QueueID.QueueStatus == 'IN MODULE':
                kiosk.QueueID.QueueStatus = 'IN MODULE'
                kiosk.QueueID.save()
                
        if logged_in_username:
            queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
            if not kiosk.QueueID:
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = current_time
                kiosk.save()
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
    }

    return render(request, 'selectmunicipality4.html', context)

def selectmunicipality5(request, kiosk_id):
    logged_in_username = request.session.get('logged_in_username')
    current_time = timezone.now()
    kiosk_username = None

    # Check and handle kiosks that have exceeded time limits
    for kiosk in Kiosk.objects.filter(KioskStatus=True).select_related('QueueID'):
        if kiosk.QueueID and kiosk.QueueID.EndTime:
            time_elapsed = current_time - kiosk.QueueID.EndTime
            if time_elapsed >= timedelta(minutes=1):
                queue_entry = kiosk.QueueID
                if queue_entry.QueueStatus == 'IN KIOSK':
                    kiosk.QueueID.delete()
                    kiosk.KioskStatus = False
                    kiosk.QueueID = None
                    kiosk.TimeDuration = None
                    kiosk.save()
        else:
            kiosk.KioskStatus = False
            kiosk.TimeDuration = None
            kiosk.save()

    try:
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        if kiosk.QueueID:
            kiosk_username = kiosk.QueueID.user.username
            if not kiosk.QueueID.QueueStatus == 'IN MODULE':
                kiosk.QueueID.QueueStatus = 'IN MODULE'
                kiosk.QueueID.save()
                
        if logged_in_username:
            queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
            if not kiosk.QueueID:
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = current_time
                kiosk.save()
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
    }

    return render(request, 'selectmunicipality5.html', context)

def selectmunicipality6(request, kiosk_id):
    logged_in_username = request.session.get('logged_in_username')
    current_time = timezone.now()
    kiosk_username = None

    # Check and handle kiosks that have exceeded time limits
    for kiosk in Kiosk.objects.filter(KioskStatus=True).select_related('QueueID'):
        if kiosk.QueueID and kiosk.QueueID.EndTime:
            time_elapsed = current_time - kiosk.QueueID.EndTime
            if time_elapsed >= timedelta(minutes=1):
                queue_entry = kiosk.QueueID
                if queue_entry.QueueStatus == 'IN KIOSK':
                    kiosk.QueueID.delete()
                    kiosk.KioskStatus = False
                    kiosk.QueueID = None
                    kiosk.TimeDuration = None
                    kiosk.save()
        else:
            kiosk.KioskStatus = False
            kiosk.TimeDuration = None
            kiosk.save()

    try:
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        if kiosk.QueueID:
            kiosk_username = kiosk.QueueID.user.username
            if not kiosk.QueueID.QueueStatus == 'IN MODULE':
                kiosk.QueueID.QueueStatus = 'IN MODULE'
                kiosk.QueueID.save()
                
        if logged_in_username:
            queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
            if not kiosk.QueueID:
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = current_time
                kiosk.save()
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
    }

    return render(request, 'selectmunicipality6.html', context)

#CATEGORIZE THE MUNICIPALITY FOR THE SORTING OF DATA FOR THE MODULE
def get_district_suffix(municipality):

    suffix_to_municipalities = {
        'D1': ['NASUGBU', 'LIAN', 'TUY', 'BALAYAN', 'CALACA', 'CALATAGAN', 'LEMERY', 'TAAL'],
        'D2': ['SAN LUIS', 'BAUAN', 'SAN PASCUAL', 'MABINI', 'TINGLOY', 'LOBO'],
        'D3': ['STO.TOMAS', 'AGONCILLO', 'TALISAY', 'TANAUAN', 'MALVAR', 'SAN NICOLAS', 'BALETE', 'MATAAS NA KAHOY', 'STA. TERESITA', 'CUENCA', 'ALITAGTAG', 'LAUREL'],
        'D4': ['SAN JOSE', 'IBAAN', 'ROSARIO', 'TAYSAN', 'PADRE GARCIA', 'SAN JUAN'],
        'D5': ['BATANGAS'], 
        'D6': ['LIPA'],  
    }
    for suffix, municipalities in suffix_to_municipalities.items():
        if municipality.upper() in municipalities:
            return suffix
    return None

def get_modules_by_type_and_municipality(module_type, municipality):

    suffix = get_district_suffix(municipality)
    if not suffix:
        return None  # Municipality not found in the mapping

    # Filter the modules based on type (t, f, c), municipality, and district suffix
    modules = DistrictModules.objects.filter(
        Municipality__iexact=municipality,
        DistrictModuleID__startswith=module_type,
        DistrictModuleID__endswith=suffix
    )
    return modules

#MODULES FOR TOURIST ATTRACTIONS
def module_tourist(request, kiosk_id, municipality):
    modules = get_modules_by_type_and_municipality('t', municipality)
    if modules is None:
        return render(request, 'error.html', {'message': 'Municipality not found.'})
    return render(request, 'module_tourist.html', {'modules': modules, 'municipality': municipality})

#MODULES FOR FOOD
def module_food(request, kiosk_id, municipality):
    modules = get_modules_by_type_and_municipality('f', municipality)
    if modules is None:
        return render(request, 'error.html', {'message': 'Municipality not found.'})
    return render(request, 'module_food.html', {'modules': modules, 'municipality': municipality})

#MODULES FOR CRAFTS
def module_craft(request, kiosk_id, municipality):
    modules = get_modules_by_type_and_municipality('c', municipality)
    if modules is None:
        return render(request, 'error.html', {'message': 'Municipality not found.'})
    return render(request, 'module_craft.html', {'modules': modules, 'municipality': municipality})

#THIS IS FOR CALLING THE MODULE CONTAINER AND LAYOUT FUNCTIONS
def selectmodule(request):
    municipality = request.GET.get('municipality', '')
    
    return render(request, 'selectmodule.html',{'municipality': municipality})

#FOR THE QUIZ POINTS UNDERDEVELOPMENT
def calculate_points(remaining_seconds):

    return remaining_seconds // 10

#THE QUIZ FUNCTION UNDERDEVELOPMENT
def quiz(request):
    if 'game_session' not in request.session:
        # Start a new game session if one doesn't already exist
        questions = list(TriviaQuestion.objects.all())
        if not questions:
            return render(request, 'quiz.html', {'question': None})

        selected_question = random.choice(questions)
        request.session['game_session'] = {
            'question_id': selected_question.TriviaQuestionID,
            'reward_points': 0,
            'guesses_left': 3,
            'start_time': timezone.now().isoformat()
        }

    game_session = request.session['game_session']
    question_id = game_session['question_id']
    selected_question = TriviaQuestion.objects.get(TriviaQuestionID=question_id)

    remaining_time = (180 - (timezone.now() - timezone.datetime.fromisoformat(game_session['start_time'])).total_seconds())

    if remaining_time <= 0:
        return redirect('results')

    if request.method == 'POST':
        guess = request.POST.get('guess', '').strip().lower()
        correct = guess == selected_question.QuestionAnswer.lower()
        if correct:
            # Calculate points based on remaining time
            points = calculate_points(remaining_time)
            game_session['reward_points'] += points
            # Prepare for the next question
            game_session['guesses_left'] = 3
            messages.success(request, f'Correct answer! {points} points added.')
            # Select next question
            questions = list(TriviaQuestion.objects.exclude(TriviaQuestionID=question_id))
            if questions:
                next_question = random.choice(questions)
                game_session['question_id'] = next_question.TriviaQuestionID
            else:
                return redirect('results')
        else:
            game_session['guesses_left'] -= 1
            if game_session['guesses_left'] <= 0:
                user_reward_points, _ = RewardPoints.objects.get_or_create(user=request.user)
                user_reward_points.points += game_session['reward_points']
                user_reward_points.save()
                del request.session['game_session']
                return redirect('results')
        request.session.modified = True

    # Update the session
    request.session['game_session'] = game_session
    request.session.modified = True

    return render(request, 'quiz.html', {
        'question': selected_question.QuestionContent,
        'guesses_left': game_session['guesses_left'],
        'remaining_time': int(remaining_time),
        'reward_points': game_session['reward_points'],
        'correct': correct if 'correct' in locals() else None
    })
    
#THE RESULT OF THE QUIZ UNDERDEVELOPMENT
def results_view(request):

    reward_points = request.session.get('game_session', {}).get('reward_points', 0)

    if 'game_session' in request.session:
        del request.session['game_session']
    
    return render(request, 'results.html', {
        'reward_points': reward_points
    })