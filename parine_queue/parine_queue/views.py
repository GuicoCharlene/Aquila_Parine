from django.contrib import messages
from django.shortcuts import render, redirect
from django.db import models
from django.db.models import Case, When, Value, CharField
from .models import QueueVisitor, QueueEntry, Kiosk, Admin, Queue_Capacity, Visitor_History, DistrictModules, TriviaQuestion, RewardPoints, VisitorProgress
import random, os
from django.utils import timezone
from datetime import timedelta
from django.http import HttpResponseRedirect, JsonResponse
from .models import QueueEntry, Kiosk
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
import logging
from django.db import transaction
from django.urls import reverse
from django.db.models import F, Count, Q
from django.contrib.auth.decorators import login_required
from django.conf import settings 
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Sum

logger = logging.getLogger(__name__)

# View for the landing page
def homepage(request):
    return render(request, 'homepage.html')

# View for that handles login
def login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        is_admin_login = request.POST.get('validate_only_admin') == 'on'  # Checkbox if the user is admin

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
                    
                    # Determining the priority level based on pwd, reserve, and age values
                    if visitor.age >= 60:
                        priority = "high"
                    else:
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
        # Calculate time spent in the queue
        if queue_entry.StartTime:
            time_spent = timezone.now() - queue_entry.StartTime
            # Change priority level from low to mid
            if queue_entry.PriorityLevel == 'low' and time_spent.total_seconds() >= 180 * 60: # Minutes
                queue_entry.PriorityLevel = 'mid'
                queue_entry.save()
            # Change priority level from mid to high
            elif queue_entry.PriorityLevel == 'mid' and time_spent.total_seconds() >= 300 * 60: # Minutes
                queue_entry.PriorityLevel = 'high'
                queue_entry.save()

        available_kiosk = Kiosk.objects.filter(KioskStatus=False).first()
        if available_kiosk:
            available_kiosk.KioskStatus = True
            available_kiosk.QueueID = queue_entry
            available_kiosk.TimeDuration = timezone.now()
            available_kiosk.save()
            # Update QueueStatus to 'IN KIOSK' only if it's not already 'IN MODULE' or 'INACTIVE'
            if queue_entry.QueueStatus != 'IN MODULE':
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

    queue_entries = QueueEntry.objects.exclude(QueueStatus='IN KIOSK').exclude(QueueStatus='IN MODULE').exclude(QueueStatus='INACTIVE').select_related('user').order_by(
        Case(
            When(PriorityLevel='high', then=Value(0)),
            When(PriorityLevel='mid', then=Value(1)),
            When(PriorityLevel='low', then=Value(2)),
            default=Value(3),
            output_field=CharField(),
        ),
    )

    context = {
        'queue_entries': queue_entries,
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
            # To prevent empty input
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

    # Check and handle user in kiosks that have exceeded time wait limit
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

            kiosk_data.append(kiosk_info)

        return JsonResponse({'kiosk_data': kiosk_data})
    except Exception as e:
        logger.error(f"Error fetching kiosk data: {e}", exc_info=True)
        return JsonResponse({'error': 'Internal Server Error'}, status=500)


#user login in kiosk
@transaction.atomic
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

                # Save progress if the user was taking a quiz
                if 'game_session' in request.session:
                    game_session = request.session['game_session']
                    visitor_id = queue_entry.user_id
                    district_module_id = game_session.get('district_module_id')
                    trivia_question_id = game_session.get('trivia_question_id')

                    # Create or update VisitorProgress record
                    VisitorProgress.objects.update_or_create(
                        VisitorID_id=visitor_id,
                        DistrictModuleID_id=district_module_id,
                        defaults={'TriviaQuestionID_id': trivia_question_id}
                    )
                    
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

def history(request):
    all_queued_users = QueueEntry.objects.all().select_related('user')
    unique_user_ids = set(entry.user_id for entry in all_queued_users)

    for user_id in unique_user_ids:
        user = QueueVisitor.objects.get(VisitorID=user_id)
        # Check if the user ID exists in Visitor_History
        if not Visitor_History.objects.filter(userid=user).exists():
            # If the user ID doesn't exist, get the first queue entry for this user
            start_time_entry = all_queued_users.filter(user_id=user_id).order_by('StartTime').first()
            # Check if there is a queue entry for this user
            if start_time_entry:
                start_time = start_time_entry.StartTime
                start_date = start_time.date()
                # Create a new record in Visitor_History
                Visitor_History.objects.create(user=user.username, userid=user, date=start_date)
        else:
            # If the user ID exists, check if the date is not the same
            last_queue_entry = all_queued_users.filter(user_id=user_id).order_by('-StartTime').first()
            if last_queue_entry:
                last_queue_date = last_queue_entry.StartTime.date()
                # Check if an entry with the same user ID and date already exists
                if not Visitor_History.objects.filter(Q(userid=user) & Q(date=last_queue_date)).exists():
                    # If not, create a new record in Visitor_History
                    Visitor_History.objects.create(user=user.username, userid=user, date=last_queue_date)

    visitor_history = Visitor_History.objects.all()

    grouped_data = {}
    for entry in visitor_history:
        date = entry.date
        username = entry.user
        if date not in grouped_data:
            grouped_data[date] = {'usernames': [username], 'total_count': 1}
        else:
            grouped_data[date]['usernames'].append(username)
            grouped_data[date]['total_count'] += 1

    grouped_data = {date.date(): data for date, data in grouped_data.items()}

    context = {'grouped_data': grouped_data}

    return render(request, 'history.html', context)


def admin_district_1(request):
  # Fetch modules for District 1
    municipality = request.GET.get('municipality', '')
    
    return render(request, 'admin_district_1.html',{'municipality': municipality})

def admin_district_2(request):
 # Fetch modules for District 2
    municipality = request.GET.get('municipality', '')
    
    return render(request, 'admin_district_2.html',{'municipality': municipality})

def admin_district_3(request):
  # Fetch modules for District 3
    municipality = request.GET.get('municipality', '')
    
    return render(request, 'admin_district_3.html',{'municipality': municipality})

def admin_district_4(request):
    # Fetch modules for District 4
    municipality = request.GET.get('municipality', '')
    
    return render(request, 'admin_district_4.html',{'municipality': municipality})

def admin_district_5(request):
     # Fetch modules for District 5
    municipality = request.GET.get('municipality', '')
    
    return render(request, 'admin_district_5.html',{'municipality': municipality})

def admin_district_6(request):
 # Fetch modules for District 6
    municipality = request.GET.get('municipality', '')
    
    return render(request, 'admin_district_6.html',{'municipality': municipality})

def get_district_modules(suffix):
    # Fetch modules based on the district suffix
    modules = DistrictModules.objects.filter(DistrictModuleID__endswith=suffix)
    return modules


def add_module(request):
    if request.method == 'POST':
        module_name = request.POST.get('new_module_name')
        module_file = request.POST.get('new_module_file')
        module_image = request.FILES.get('new_module_image')
        municipality = request.POST.get('municipality_name')
        moduletype = request.POST.get('moduletype_suffix')

        # Get the district suffix for the municipality
        district_suffix = get_district_suffix(municipality)

        if district_suffix:
            # Get existing modules to determine the numeric part
            existing_modules = DistrictModules.objects.filter(DistrictModuleID__startswith=moduletype, DistrictModuleID__endswith=district_suffix)

            # Extract the numeric parts
            numeric_parts = [int(module.DistrictModuleID[len(moduletype):-len(district_suffix)]) for module in existing_modules]

            # Find the maximum numeric part
            if numeric_parts:
                numeric_part = max(numeric_parts) + 1
            else:
                numeric_part = 1

            # Generate the DistrictModuleID
            district_module_id = f'{moduletype}{str(numeric_part).zfill(3)}{district_suffix}'  # Ensure numeric part is padded with zeros

            # Save the module to the database with the generated DistrictModuleID
            new_module = DistrictModules(DistrictModuleID=district_module_id, Municipality=municipality, ModuleName=module_name, ModuleContent=module_image, ModuleFile=module_file)

            if module_image:  # Check if module_image is not None
                new_module.ModuleContent = os.path.basename(module_image.name)  # Save only the filename

                # Save the uploaded image to the media directory
                image_path = os.path.join(settings.MEDIA_ROOT, module_image.name)
                default_storage.save(image_path, ContentFile(module_image.read()))

            new_module.save()

    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))
def delete_module(request):
    if request.method == 'POST':
        module_id = request.POST.get('module_id')    
        try:
            module_to_delete = DistrictModules.objects.get(DistrictModuleID=module_id)
            
            # Delete associated image file if it exists
            if module_to_delete.ModuleContent:
                image_path = module_to_delete.ModuleContent.path  # Get the path of the image file
                if default_storage.exists(image_path):
                    default_storage.delete(image_path)  # Delete the image file
            module_to_delete.delete()
        except DistrictModules.DoesNotExist:
            pass
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))
  
def save_module_changes(request):
    if request.method == 'POST':
        module_id = request.POST.get('module_id')
        new_module_name = request.POST.get('new_module_name')
        new_module_image = request.FILES.get('image_file')  # Get the uploaded image file
        new_module_file = request.POST.get('new_module_file')

        try:
            module = DistrictModules.objects.get(DistrictModuleID=module_id)
            if module.ModuleName == new_module_name and module.ModuleFile == new_module_file:
                if new_module_image:
                    module.ModuleContent = os.path.basename(new_module_image.name)  # Save only the filename
                    module.save()
                    messages.info(request, "No changes made to the module.")
            else:
                module.ModuleName = new_module_name
                if new_module_file is not None and new_module_file != "":
                    module.ModuleFile = new_module_file
                else:
                    module.ModuleFile = "None"  # Set to "None" if the field is empty
                if new_module_image:
                    # Save the uploaded image to the media directory
                    image_path = os.path.join(settings.MEDIA_ROOT, new_module_image.name)
                    default_storage.save(image_path, ContentFile(new_module_image.read()))
                    module.ModuleContent = os.path.basename(new_module_image.name)  # Save only the filename
                module.save()
                messages.success(request, "Module updated successfully.")
        except DistrictModules.DoesNotExist:
            messages.error(request, "Module does not exist.")

        return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))

def admin_module_tourist(request, municipality):
    modules = get_modules_by_type_and_municipality('t', municipality)
    if modules is None:
        return render(request, 'error.html', {'message': 'Municipality not found.'})
    return render(request, 'admin_module_tourist.html', {'modules': modules, 'municipality': municipality})

#MODULES FOR FOOD
def admin_module_food(request, municipality):
    modules = get_modules_by_type_and_municipality('f', municipality)
    if modules is None:
        return render(request, 'error.html', {'message': 'Municipality not found.'})
    return render(request, 'admin_module_food.html', {'modules': modules, 'municipality': municipality})

#MODULES FOR CRAFTS
def admin_module_craft(request, municipality):
    modules = get_modules_by_type_and_municipality('c', municipality)
    if modules is None:
        return render(request, 'error.html', {'message': 'Municipality not found.'})
    return render(request, 'admin_module_craft.html', {'modules': modules, 'municipality': municipality})

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
        return None  # Municipality not found in the sorting and searching

    # Filter the modules based on type (t, f, c), municipality, and district suffix
    modules = DistrictModules.objects.filter(
        Municipality__iexact=municipality,
        DistrictModuleID__startswith=module_type,
        DistrictModuleID__endswith=suffix
    )
    return modules


def module_tourist(request, kiosk_id, municipality):
    modules = get_modules_by_type_and_municipality('t', municipality)
    if modules is None:
        return render(request, 'error.html', {'message': 'Municipality not found.'})
    
    # Display the module view
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

def take_quiz(request):
   
    return render(request, 'take_quiz.html')

logger = logging.getLogger(__name__)

def fetch_quiz_questions(module_type, municipality):
    # Filter questions based on module type and municipality
    questions = TriviaQuestion.objects.filter(ModuleType=module_type, Municipality__iexact=municipality)
    return questions

def quiz(request):
    if 'game_session' not in request.session:
        # Initialize session data if it doesn't exist
        module_type = request.GET.get('module_type')
        municipality = request.GET.get('municipality')
        kiosk_id = request.GET.get('kiosk_id')

        try:
            kiosk = Kiosk.objects.get(KioskID=kiosk_id)
            queue_id = kiosk.QueueID
            visitor_id = queue_id.user.pk

            questions = fetch_quiz_questions(module_type, municipality)
            if not questions:
                return render(request, 'quiz.html', {'question_content': None})

            selected_question_ids = [question.TriviaQuestionID for question in questions]
            request.session['game_session'] = {
                'question_ids': selected_question_ids,
                'answered_question_ids': [],
                'correct_answer_ids': [],
                'reward_points': 0,
                'guesses_left': 3,
                'start_time': timezone.now().isoformat(),
                'module_type': module_type,
                'municipality': municipality,
                'kiosk_id': kiosk_id,
                'VisitorID': visitor_id,
                'incorrect_guesses': 0,
                'current_question_id': None  # Add a field to track the current question
            }

            if not RewardPoints.objects.filter(user_id=visitor_id).exists():
                RewardPoints.objects.create(user_id=visitor_id, TotalPoints=5)

        except:
            logger.error("Kiosk matching query does not exist.")

    else:
        game_session = request.session.get('game_session')
        visitor_id = game_session.get('VisitorID')
        module_type = game_session.get('module_type')
        municipality = game_session.get('municipality')

        answered_questions = RewardPoints.objects.filter(user_id=visitor_id).values_list('TriviaQuestionID', flat=True)
        all_questions = fetch_quiz_questions(module_type, municipality)
        remaining_questions = [q for q in all_questions if q.TriviaQuestionID not in answered_questions]

        remaining_question_ids = [question.TriviaQuestionID for question in remaining_questions]
        request.session['game_session']['question_ids'] = remaining_question_ids

    game_session = request.session.get('game_session')
    question_ids = game_session['question_ids']
    answered_question_ids = game_session.get('answered_question_ids', [])

    remaining_question_ids = [q_id for q_id in question_ids if q_id not in answered_question_ids]

    if remaining_question_ids:
        if game_session['current_question_id'] is None:
            question_id = random.choice(remaining_question_ids)
        else:
            question_id = game_session['current_question_id']

        selected_question = TriviaQuestion.objects.get(TriviaQuestionID=question_id)

        initial_start_time = timezone.datetime.fromisoformat(game_session['start_time'])
        remaining_time = (60 - (timezone.now() - initial_start_time).total_seconds())
        if remaining_time <= 0:
            return redirect('results')

        correct = None
        if request.method == 'POST':
            guess = request.POST.get('guess', '').strip().lower()
            correct_answer = selected_question.Images.strip().lower()
            correct = guess == correct_answer

            if correct:
                game_session['answered_question_ids'].append(question_id)
                game_session['correct_answer_ids'].append(question_id)
                game_session['guesses_left'] = 3
                game_session['incorrect_guesses'] = 0
                game_session['current_question_id'] = None

                reward_points_instance, created = RewardPoints.objects.get_or_create(
                    user_id=visitor_id,
                    TriviaQuestionID=question_id,  # Associate the question with TriviaQuestionID
                    defaults={'TotalPoints': 0}
                )
                reward_points_instance.TotalPoints += 1
                reward_points_instance.save()

                game_session['reward_points'] = RewardPoints.objects.filter(user_id=visitor_id).aggregate(Sum('TotalPoints'))['TotalPoints__sum']
            else:
                # Only decrease guesses_left if the guess is incorrect
                if game_session['incorrect_guesses'] < 2:
                    game_session['guesses_left'] -= 1
                    game_session['incorrect_guesses'] += 1

            request.session.modified = True

        incorrect_guesses = game_session['incorrect_guesses']

        return render(request, 'quiz.html', {
            'question_content': selected_question.QuestionContent,
            'question_image': selected_question.Images,
            'random_images': TriviaQuestion.objects.exclude(TriviaQuestionID=question_id).order_by('?')[:3].values_list('Images', flat=True),
            'guesses_left': game_session['guesses_left'],
            'remaining_time': int(remaining_time),
            'reward_points': game_session.get('reward_points', 0),
            'correct': correct,
            'module_type': game_session['module_type'],
            'municipality': game_session['municipality'],
            'incorrect_guesses': incorrect_guesses,
        })
    else:
        return redirect('done_quiz')

def done_quiz(request):
    return render(request, 'done_quiz.html')

def results_view(request):
    visitor_id = request.session.get('game_session').get('VisitorID')
    total_points_entry = RewardPoints.objects.filter(user_id=visitor_id).aggregate(total_points=models.Sum('TotalPoints'))
    total_points = total_points_entry['total_points'] if total_points_entry['total_points'] else 0

    if 'game_session' in request.session:
        del request.session['game_session']
    
    return render(request, 'results.html', {'total_points': total_points})


