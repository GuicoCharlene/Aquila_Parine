from operator import le
from pyexpat import model
from django.contrib import messages
from django.shortcuts import render, redirect
from django.db import models
from django.db.models import Case, When, Value, CharField
from .models import QueueVisitor, QueueEntry, Kiosk, Admin, Queue_Capacity, Visitor_History, DistrictModules, TriviaQuestion, RewardPoints, VisitorProgress
import random, os
from django.views.decorators.http import require_http_methods
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
from datetime import datetime
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

    # Aging mechanism: Increase priority level based on waiting time
    for queue_entry in QueueEntry.objects.exclude(QueueStatus='IN KIOSK').exclude(QueueStatus='IN MODULE').exclude(QueueStatus='INACTIVE').select_related('user').order_by('PriorityLevel'):
        if queue_entry.StartTime:
            time_spent = timezone.now() - queue_entry.StartTime
	        # Change priority level from low to mid
            if queue_entry.PriorityLevel == 'low' and time_spent.total_seconds() >= 60 * 60:  # first number is equivalent to minutes
                queue_entry.PriorityLevel = 'mid'
                queue_entry.save()
	        # Change priority level from mid to high
            elif queue_entry.PriorityLevel == 'mid' and time_spent.total_seconds() >= 120 * 60:  # first number is equivalent to minutes
                queue_entry.PriorityLevel = 'high'
                queue_entry.save()

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

    total_points = 0  # Default value for total points

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

        # Fetch total points for the current date
        if logged_in_username:
            visitor_id = queue_entry.user.pk
            total_points_entry = RewardPoints.objects.filter(user_id=visitor_id, create_time__date=timezone.now().date()).aggregate(total_points=Sum('TotalPoints'))
            total_points = total_points_entry.get('total_points', 0)

    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
        'total_points': total_points,
    }
    return render(request, 'selectdistrict.html', context)

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
        module_first = request.FILES.get('new_first_image')
        module_second = request.FILES.get('new_second_image')
        module_third = request.FILES.get('new_third_image')
        municipality = request.POST.get('municipality_name')
        module_location = request.POST.get('new_module_location')
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
            new_module = DistrictModules(DistrictModuleID=district_module_id, Municipality=municipality, ModuleName=module_name,ModuleLocation=module_location, FirstImage = module_first, SecondImage= module_second,ThirdImage=module_third,ModuleContent=module_image, ModuleFile=module_file)

            if module_image:  # Check if module_image is not None
                new_module.ModuleContent = os.path.basename(module_image.name)  # Save only the filename

                # Save the uploaded image to the media directory
                image_path = os.path.join(settings.MEDIA_ROOT, module_image.name)
                default_storage.save(image_path, ContentFile(module_image.read()))
            if module_first:  # Check if module_image is not None
                new_module.FirstImage = os.path.basename(module_first.name)  # Save only the filename

                # Save the uploaded image to the media directory
                image_path = os.path.join(settings.MEDIA_ROOT, module_first.name)
                default_storage.save(image_path, ContentFile(module_first.read()))

            if module_second:  # Check if module_image is not None
                new_module.SecondImage = os.path.basename(module_second.name)  # Save only the filename

                # Save the uploaded image to the media directory
                image_path = os.path.join(settings.MEDIA_ROOT, module_second.name)
                default_storage.save(image_path, ContentFile(module_second.read()))

            if module_third:  # Check if module_image is not None
                new_module.ThirdImage = os.path.basename(module_third.name)  # Save only the filename

                # Save the uploaded image to the media directory
                image_path = os.path.join(settings.MEDIA_ROOT, module_third.name)
                default_storage.save(image_path, ContentFile(module_third.read()))

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
        new_module_first = request.FILES.get('first_image')
        new_module_second = request.FILES.get('second_image')
        new_module_third = request.FILES.get('third_image')
        new_module_location = request.POST.get('new_module_location')
        try:
            module = DistrictModules.objects.get(DistrictModuleID=module_id)
            if module.ModuleName == new_module_name and module.ModuleFile == new_module_file == new_module_location:
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
                if new_module_location is not None and new_module_location != "":
                    module.ModuleLocation = new_module_location
                else:
                    module.ModuleLocation = "None"  # Set to "None" if the field is empty
                if new_module_image:
                    # Save the uploaded image to the media directory
                    image_path = os.path.join(settings.MEDIA_ROOT, new_module_image.name)
                    default_storage.save(image_path, ContentFile(new_module_image.read()))
                    module.ModuleContent = os.path.basename(new_module_image.name)  # Save only the filename
                if new_module_first:
                    # Save the uploaded image to the media directory
                    image_path = os.path.join(settings.MEDIA_ROOT, new_module_first.name)
                    default_storage.save(image_path, ContentFile(new_module_first.read()))
                    module.FirstImage = os.path.basename(new_module_first.name)  # Save only the filename
                if new_module_second:
                    # Save the uploaded image to the media directory
                    image_path = os.path.join(settings.MEDIA_ROOT, new_module_second.name)
                    default_storage.save(image_path, ContentFile(new_module_second.read()))
                    module.SecondImage = os.path.basename(new_module_second.name)  # Save only the filename
                if new_module_third:
                    # Save the uploaded image to the media directory
                    image_path = os.path.join(settings.MEDIA_ROOT, new_module_third.name)
                    default_storage.save(image_path, ContentFile(new_module_third.read()))
                    module.ThirdImage = os.path.basename(new_module_third.name)  # Save only the filename
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


def add_quiz(request):
    if request.method == 'POST':
        quiz_file = request.POST.get('new_quiz_file')
        quiz_image = request.FILES.get('new_quiz_image')
        municipality = request.POST.get('municipality_name')
        moduletype = request.POST.get('quiztype')
   
        # Save the module to the database with the generated TriviaQuestionID
        new_quiz = TriviaQuestion(Municipality=municipality, ModuleType=moduletype, Images=quiz_image, QuestionContent=quiz_file)

        if quiz_image:  # Check if quiz_image is not None
            new_quiz.Images = os.path.basename(quiz_image.name)  # Save only the filename

            # Save the uploaded image to the media directory
            image_path = os.path.join(settings.MEDIA_ROOT, quiz_image.name)
            default_storage.save(image_path, ContentFile(quiz_image.read()))
                
        new_quiz.save()

    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))

def delete_quiz(request):
    if request.method == 'POST':
        quiz_id = request.POST.get('quiz_id')    
        try:
            quiz_to_delete = TriviaQuestion.objects.get(TriviaQuestionID=quiz_id)
            
            # Delete associated image file if it exists
            if quiz_to_delete.Images:
                image_path = quiz_to_delete.Images.path  # Get the path of the image file
                if default_storage.exists(image_path):
                    default_storage.delete(image_path)  # Delete the image file
            quiz_to_delete.delete()
        except TriviaQuestion.DoesNotExist:
            pass
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))
  
def save_quiz_changes(request):
    if request.method == 'POST':
        quiz_id = request.POST.get('quiz_id')
        new_quiz_name = request.POST.get('quiz_name')
        new_quiz_image = request.FILES.get('image_file')  # Get the uploaded image file
        new_quiz_file = request.POST.get('new_quiz_file')

        try:
            save_quiz = TriviaQuestion.objects.get(TriviaQuestionID=quiz_id)
            if save_quiz.Municipality == new_quiz_name and save_quiz.QuestionContent == new_quiz_file:
                if new_quiz_image:
                    save_quiz.Images = os.path.basename(new_quiz_image.name) # Set the Images field directly with the file object
                    save_quiz.save()
                    messages.info(request, "No changes made to the module.")
            else:
                save_quiz.Municipality = new_quiz_name  # Update the Municipality field
                if new_quiz_file is not None and new_quiz_file != "":
                    save_quiz.QuestionContent = new_quiz_file
                else:
                    save_quiz.QuestionContent = "None"  # Set to "None" if the field is empty
                if new_quiz_image:
                    # Save the uploaded image to the media directory
                    image_path = os.path.join(settings.MEDIA_ROOT, new_quiz_image.name)
                    default_storage.save(image_path, ContentFile(new_quiz_image.read()))
                    save_quiz.Images = new_quiz_image  # Set the Images field directly with the file object
                
                save_quiz.save()
        except TriviaQuestion.DoesNotExist:
            messages.error(request, "Module does not exist.")

        return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard'))

def admin_quiz_tourist(request, municipality):
    questions = TriviaQuestion.objects.filter(ModuleType='module_tourist', Municipality__iexact=municipality)
    return render(request, 'admin_quiz_tourist.html', {'questions': questions, 'municipality': municipality})

def admin_quiz_food(request, municipality):
    questions = TriviaQuestion.objects.filter(ModuleType='module_food', Municipality__iexact=municipality)
    return render(request, 'admin_quiz_food.html', {'questions': questions, 'municipality': municipality})

def admin_quiz_craft(request, municipality):
    questions = TriviaQuestion.objects.filter(ModuleType='module_craft', Municipality__iexact=municipality)
    return render(request, 'admin_quiz_craft.html', {'questions': questions, 'municipality': municipality})

def selectmunicipality1(request, kiosk_id):
    total_points = 0  # Default value for total points
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
                
        # Fetch total points for the current date if a user is logged in
        if logged_in_username:
            visitor_id = queue_entry.user.pk
            total_points_entry = RewardPoints.objects.filter(user_id=visitor_id, create_time__date=timezone.now().date()).aggregate(total_points=Sum('TotalPoints'))
            total_points = total_points_entry.get('total_points', 0)
            
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
        'total_points': total_points,
    }

    return render(request, 'selectmunicipality1.html', context)


def selectmunicipality2(request, kiosk_id):
    total_points = 0
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
                
        # Fetch total points for the current date if a user is logged in
        if logged_in_username:
            visitor_id = queue_entry.user.pk
            total_points_entry = RewardPoints.objects.filter(user_id=visitor_id, create_time__date=timezone.now().date()).aggregate(total_points=Sum('TotalPoints'))
            total_points = total_points_entry.get('total_points', 0)
            
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
        'total_points': total_points,
    }
    return render(request, 'selectmunicipality2.html', context)

def selectmunicipality3(request, kiosk_id):
    total_points = 0
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
                
        # Fetch total points for the current date if a user is logged in
        if logged_in_username:
            visitor_id = queue_entry.user.pk
            total_points_entry = RewardPoints.objects.filter(user_id=visitor_id, create_time__date=timezone.now().date()).aggregate(total_points=Sum('TotalPoints'))
            total_points = total_points_entry.get('total_points', 0)
            
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
        'total_points': total_points,
    }
    return render(request, 'selectmunicipality3.html', context)


def selectmunicipality4(request, kiosk_id):
    total_points = 0
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
                
        # Fetch total points for the current date if a user is logged in
        if logged_in_username:
            visitor_id = queue_entry.user.pk
            total_points_entry = RewardPoints.objects.filter(user_id=visitor_id, create_time__date=timezone.now().date()).aggregate(total_points=Sum('TotalPoints'))
            total_points = total_points_entry.get('total_points', 0)
            
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
        'total_points': total_points,
    }
    return render(request, 'selectmunicipality4.html', context)

def selectmunicipality5(request, kiosk_id):
    total_points = 0
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
                
        # Fetch total points for the current date if a user is logged in
        if logged_in_username:
            visitor_id = queue_entry.user.pk
            total_points_entry = RewardPoints.objects.filter(user_id=visitor_id, create_time__date=timezone.now().date()).aggregate(total_points=Sum('TotalPoints'))
            total_points = total_points_entry.get('total_points', 0)
            
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
        'total_points': total_points,
    }
    return render(request, 'selectmunicipality5.html', context)

def selectmunicipality6(request, kiosk_id):
    total_points = 0
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
                
        # Fetch total points for the current date if a user is logged in
        if logged_in_username:
            visitor_id = queue_entry.user.pk
            total_points_entry = RewardPoints.objects.filter(user_id=visitor_id, create_time__date=timezone.now().date()).aggregate(total_points=Sum('TotalPoints'))
            total_points = total_points_entry.get('total_points', 0)
            
    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")
    except QueueEntry.DoesNotExist:
        messages.error(request, "No user assigned to this kiosk.")

    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': logged_in_username,
        'total_points': total_points,
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
        return render(request, 'no_data.html')
    return render(request, 'module_tourist.html', {'modules': modules, 'municipality': municipality})

#MODULES FOR FOOD
def module_food(request, kiosk_id, municipality):
    modules = get_modules_by_type_and_municipality('f', municipality)
    if modules is None:
        return render(request, 'no_data.html')
    return render(request, 'module_food.html', {'modules': modules, 'municipality': municipality})

#MODULES FOR CRAFTS
def module_craft(request, kiosk_id, municipality):
    modules = get_modules_by_type_and_municipality('c', municipality)
    if modules is None:
        return render(request, 'no_data.html')
    return render(request, 'module_craft.html', {'modules': modules, 'municipality': municipality})

#THIS IS FOR CALLING THE MODULE CONTAINER AND LAYOUT FUNCTIONS
def selectmodule(request):
    municipality = request.GET.get('municipality', '')
    
    return render(request, 'selectmodule.html',{'municipality': municipality})

def take_quiz(request):
   
    return render(request, 'take_quiz.html')

logger = logging.getLogger(__name__)

def fetch_quiz_questions(module_type, municipality, visitor_id):
    # Fetch questions that haven't been answered by the user, filtered by module type and municipality
    answered_questions = RewardPoints.objects.filter(
        user_id=visitor_id, 
        TriviaQuestionID__isnull=False,
        create_time__gte=timezone.now() - timedelta(days=1)  # Filter based on the create time within the last 24 hours
    ).values_list('TriviaQuestionID', flat=True)


    questions = TriviaQuestion.objects.exclude(TriviaQuestionID__in=answered_questions) \
                                      .filter(ModuleType=module_type, Municipality__iexact=municipality) \
                                      .order_by('ModuleType', 'Municipality')

    return questions

def quiz(request):
    # Define questions variable at the top so it's available in the entire function scope
    questions = None

    if 'game_session' not in request.session:
        module_type = request.GET.get('module_type', '')
        municipality = request.GET.get('municipality', '')
        kiosk_id = request.GET.get('kiosk_id', '')

        try:
            kiosk = Kiosk.objects.get(KioskID=kiosk_id)
            visitor_id = kiosk.QueueID.user.pk

            # Check if the visitor has already completed the quiz for this module type and municipality
            visitor_progress = VisitorProgress.objects.filter(VisitorID_id=visitor_id,
                                                              Municipality__iexact=municipality,
                                                              ModuleType=module_type,
                                                              Status='DONE',
                                                              DateCompleted=timezone.now().date()).exists()
            if visitor_progress:
                # Redirect to the done_quiz page if the visitor has already completed the quiz
                return redirect('done_quiz')

            questions = fetch_quiz_questions(module_type, municipality, visitor_id)

            if not questions.exists():
                return render(request, 'quiz.html', {'message': 'No questions available.'})

            selected_question_ids = list(questions.values_list('TriviaQuestionID', flat=True))

            request.session['game_session'] = {
                'selected_questions': selected_question_ids,
                'answered_questions': [],
                'reward_points': 0,
                'visitor_id': visitor_id,
                'current_question_index': 0,
                'total_questions': len(selected_question_ids),
                'module_type': module_type,
                'municipality': municipality,
            }
            return redirect('quiz')
        except Kiosk.DoesNotExist:
            return HttpResponse("Error: Kiosk not found.", status=404)
    else:
        game_session = request.session['game_session']
        visitor_id = game_session['visitor_id']
        module_type = game_session['module_type']
        municipality = game_session['municipality']
        # Fetch questions for the existing game session if not a POST request or for the first POST request handling
        if questions is None:
            questions = fetch_quiz_questions(module_type, municipality, visitor_id)

        if request.method == 'POST':
            process_submitted_answer(request, game_session, questions)
        return display_next_question_or_finish_quiz(request)

def process_submitted_answer(request, game_session, questions):
    current_question_index = game_session['current_question_index']
    selected_question_ids = game_session['selected_questions']

    if current_question_index < len(selected_question_ids):
        current_question_id = selected_question_ids[current_question_index]
        is_correct = request.POST.get('is_correct', 'false') == 'true'
        points_for_current_question = 1 if is_correct else 0
        visitor_id = game_session.get('visitor_id', None)
        module_type = game_session.get('module_type', '')  # Retrieve module_type from game_session
        municipality = game_session.get('municipality', '')  # Retrieve municipality from game_session

        if visitor_id:
            # Now passing module_type and municipality as arguments
            update_or_create_reward_points(visitor_id, points_for_current_question, current_question_id, module_type, municipality)
            game_session['current_question_index'] += 1
            game_session['answered_questions'].append(current_question_id)
            request.session.modified = True


def display_next_question_or_finish_quiz(request):
    game_session = request.session['game_session']
    
    if game_session['current_question_index'] >= len(game_session['selected_questions']):
        return redirect('results')
    else:
        next_question_id = game_session['selected_questions'][game_session['current_question_index']]
        current_question = TriviaQuestion.objects.get(TriviaQuestionID=next_question_id)
        
        # Increment is done here to prepare for the next question, ensuring `current_question_index` is always pointing to the next question
        return render(request, 'quiz.html', {
            'question_content': current_question.QuestionContent,
            'question_image': current_question.Images,
            'random_images': list(TriviaQuestion.objects.exclude(TriviaQuestionID=current_question.TriviaQuestionID).order_by('?')[:3].values_list('TriviaQuestionID', 'Images')),
            'reward_points': game_session['reward_points'],
            'total_questions': game_session['total_questions']
        })
def update_visitor_progress(visitor_id, module_type, municipality, date_completed):
    # Check if there's already a progress for the given date
    visitor_progress_exists = VisitorProgress.objects.filter(
        VisitorID_id=visitor_id,
        Municipality=municipality,
        ModuleType=module_type,
        Status='DONE',
        DateCompleted=date_completed
    ).exists()

    # If no progress for the given date exists, create a new row
    if not visitor_progress_exists:
        VisitorProgress.objects.create(
            VisitorID_id=visitor_id,
            Municipality=municipality,
            ModuleType=module_type,
            Status='DONE',
            DateCompleted=date_completed
        )

    # Check if the visitor has completed all required module types for the municipality
    required_modules = ['module_tourist', 'module_food', 'module_craft']
    completed_modules = VisitorProgress.objects.filter(
        VisitorID_id=visitor_id,
        Municipality=municipality,
        Status='DONE',
        DateCompleted=date_completed
    ).values_list('ModuleType', flat=True)
    
    if all(module in completed_modules for module in required_modules):
        # Add 5 extra points to the total points if all required modules are completed
        add_extra_points(visitor_id, municipality)
def add_extra_points(visitor_id, municipality):
    # Check if there's already a reward entry for today
    today = timezone.now().date()
    reward_entry = RewardPoints.objects.filter(
        user_id=visitor_id,
        Municipality=municipality,
        create_time__date=today
    ).first()

    if not reward_entry:
        extra_points_id = None  # Adjust this based on how your database is structured
        defaults = {
            'TotalPoints': 5,
            'create_time': timezone.now(),
            'update_time': timezone.now()
        }
        RewardPoints.objects.create(
            user_id=visitor_id,
            Municipality=municipality,
            TriviaQuestionID_id=extra_points_id,  # Adjust based on your model fields
            **defaults
        )
    else:
        if reward_entry.create_time.date() != today:
            # Create new row if existing entry is not for the same date
            extra_points_id = None  # Adjust this based on how your database is structured
            defaults = {
                'TotalPoints': 5,
                'create_time': timezone.now(),
                'update_time': timezone.now()
            }
            RewardPoints.objects.create(
                user_id=visitor_id,
                Municipality=municipality,
                TriviaQuestionID_id=extra_points_id,  # Adjust based on your model fields
                **defaults
            )
        else:
            reward_entry.TotalPoints += 5
            reward_entry.update_time = timezone.now()
            reward_entry.save()

def update_or_create_reward_points(visitor_id, points_to_add, trivia_question_id, module_type, municipality):
    # Lookup criteria for existing entry
    lookup_criteria = {
        'user_id': visitor_id, 
        'TriviaQuestionID_id': trivia_question_id,
        'ModuleType': module_type, 
        'Municipality': municipality
    }
    # Retrieve existing entry if any
    existing_entry = RewardPoints.objects.filter(**lookup_criteria).first()

    # Check if the existing entry is for the same date
    if existing_entry and existing_entry.create_time.date() == timezone.now().date():
        # Update existing entry
        existing_entry.TotalPoints += points_to_add
        existing_entry.update_time = timezone.now()
        existing_entry.save()
    else:
        # Create new entry
        defaults = {
            'TotalPoints': points_to_add, 
            'create_time': timezone.now(), 
            'update_time': timezone.now()
        }
        RewardPoints.objects.create(**lookup_criteria, **defaults)


def results_view(request):
    visitor_id = request.session.get('game_session', {}).get('visitor_id')
    module_type = request.session.get('game_session', {}).get('module_type', '')
    municipality = request.session.get('game_session', {}).get('municipality', '')
    
    # Update the visitor's progress for the same date as today
    update_visitor_progress(visitor_id, module_type, municipality, timezone.now().date())

    total_points_entry = RewardPoints.objects.filter(user_id=visitor_id).aggregate(total_points=Sum('TotalPoints'))
    total_points = total_points_entry.get('total_points', 0)
       # Store total points in session
    request.session['total_points'] = total_points
    # Clear the game session after updating visitor progress and before rendering results
    if 'game_session' in request.session:
        del request.session['game_session']
    
    return render(request, 'results.html', {'total_points': total_points})

@require_http_methods(["POST"])
@csrf_exempt
def get_municipality_status(request):
    selected_municipality = request.POST.get('municipality_name')
    overall_status, percentage_done = get_module_status_for_municipality(selected_municipality)
    return JsonResponse({'status': overall_status, 'percentage': percentage_done})

def get_module_status_for_municipality(selected_municipality):
 
    module_types = ['module_tourist', 'module_food', 'module_craft']
    total_modules = len(module_types)

    total_done = 0
    for module_type in module_types:
        # Check if any progress exists for this module type in the given municipality
        progress_exists = VisitorProgress.objects.filter(
            Municipality=selected_municipality,
            ModuleType=module_type,
            Status='DONE'
        ).exists()

        # Increment total_done if progress exists
        if progress_exists:
            total_done += 1
        
    # Calculate the percentage of completion
    percentage_done = (total_done / total_modules) * 100

    # Set the status based on the percentage of completion
    if percentage_done == 100:
        overall_status = 'DONE'
    elif percentage_done > 0:
        overall_status = 'IN PROGRESS'
    else:
        overall_status = 'NOT STARTED'

    return overall_status, percentage_done


def done_quiz(request):
    return render(request, 'done_quiz.html')

def no_data(request):
    return render(request, 'no_data.html')