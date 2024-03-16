from django.contrib import messages
from django.shortcuts import render, redirect
from .models import QueueVisitor, QueueEntry, Kiosk, Admin, Queue_Capacity
from django.utils import timezone
from datetime import timedelta
from django.http import HttpResponseRedirect, JsonResponse
from .models import QueueEntry, Kiosk
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from .utils import ensure_kiosk_count
from django.core.exceptions import ObjectDoesNotExist
import logging
from django.db import transaction
from django.urls import reverse


logger = logging.getLogger(__name__)


# Define a view that triggers the function
def trigger_kiosk_count(request):
    ensure_kiosk_count()  # Call the function here
    return HttpResponse("Kiosk count ensured successfully!")

# View for the landing page
def landing(request):
    return render(request, 'landing.html')

# View for the homepage that handles login
def homepage(request):
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
                return redirect('homepage')  # Redirect back to the homepage for another login attempt
        else:
            # Visitor login logic
            try:
                # Check the total number of users in the queue
                total_users_in_queue = QueueEntry.objects.count()
                
                # Get the queue capacity limit
                queue_capacity_limit = Queue_Capacity.objects.values_list('limit', flat=True).first()
                
                # Check if the total users in the queue is less than the capacity limit
                if total_users_in_queue < queue_capacity_limit:
                    visitor = QueueVisitor.objects.get(username=username, password=password)
                    request.session['logged_in_username'] = username
                    
                    # Determining priority based on pwd and reserve values
                    priority = "high" if visitor.pwd else "mid" if visitor.reserve else "low"
                    
                    queue_entry, created = QueueEntry.objects.get_or_create(user=visitor, defaults={'PriorityLevel': priority, 'QueueStatus': 'WAITING', 'StartTime': timezone.now()})
                    
                    if created:
                        messages.success(request, 'You have been successfully added to the queue.')
                    else:
                        messages.info(request, 'You are already in the queue.')
                    
                    return redirect('queue')
                else:
                    messages.error(request, 'Queue is at full capacity. Please try again later.')
                    return redirect('homepage')
                
            except QueueVisitor.DoesNotExist:
                messages.error(request, 'Invalid username or password')
                return redirect('homepage')
    else:
        # If it's not a POST request, just show the login form
        return render(request, 'homepage.html')

# View for displaying the queue page
def queue(request):
    return render(request, 'queue.html')

#views for queue and kiosk
def queue_list(request):
    is_admin = request.session.get('is_admin', False)
    
    # Update kiosk status and delete associated queue entries for timed-out sessions
    for kiosk in Kiosk.objects.filter(KioskStatus=True):
        if kiosk.TimeDuration and (timezone.now() - kiosk.TimeDuration > timedelta(minutes=5)):
            if kiosk.QueueID:
                kiosk.QueueID.delete()  # Delete the associated queue entry
            kiosk.KioskStatus = False
            kiosk.QueueID = None
            kiosk.TimeDuration = None
            kiosk.save()

    # Assign users from the queue to available kiosks
    for queue_entry in QueueEntry.objects.exclude(QueueStatus='IN KIOSK').select_related('user').order_by('PriorityLevel'):
        available_kiosk = Kiosk.objects.filter(KioskStatus=False).first()
        if available_kiosk:
            available_kiosk.KioskStatus = True
            available_kiosk.QueueID = queue_entry
            available_kiosk.TimeDuration = timezone.now()
            available_kiosk.save()
            # Update queue entry status and end time
            queue_entry.EndTime = timezone.now()
            queue_entry.QueueStatus = 'IN KIOSK'
            queue_entry.save(update_fields=['QueueStatus', 'EndTime'])

    # Prepare data for displaying in the template
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
        'queue_entries': QueueEntry.objects.exclude(QueueStatus='IN KIOSK').select_related('user').order_by('PriorityLevel'),
        'kiosks_data': kiosks_data,
        'is_admin': is_admin,
        'logged_in_username': request.session.get('logged_in_username', None),
    }

    return render(request, 'queue_list.html', context)

# View for the admin page
def adminpage(request):
    view_list = True  # Always show the queue list

    queue_capacity_value = Queue_Capacity.objects.values_list('limit', flat=True).first()
    if view_list:
        queue_entries = QueueEntry.objects.all().select_related('user').order_by('PriorityLevel')
        
        # for entry in queue_entries:
        #     if entry.StartTime and timezone.now() - entry.EndTime > timedelta(minutes=5):
        #         entry.delete()
    
    context = {
        'queue_entries': queue_entries,
        'view_list': view_list,
        'logged_in_username': request.session.get('logged_in_username', None),
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
    logged_in_username = None
    
    if request.method == 'POST' and 'logout_button' in request.POST:
        # Clear the user's queue entry if they log out
        logged_in_username = request.session.get('logged_in_username')
        if logged_in_username:
            try:
                # Retrieve the user's queue entry associated with the kiosk
                queue_entry = QueueEntry.objects.get(user__username=logged_in_username, kiosk=kiosk_id)
                queue_entry.delete()
                messages.success(request, 'Successfully logged out and removed from the queue.')
            except QueueEntry.DoesNotExist:
                messages.error(request, 'No queue entry found for the logged-in user.')
        else:
            messages.error(request, 'No user is currently logged in.')

        return redirect('/kiosk_logout/')  

    # Ensure that the kiosk data is refreshed
    ensure_kiosk_count()
    
        # # Remove QueueID for users who entered the queue more than 5 minutes ago
    five_minutes_ago = timezone.now() - timezone.timedelta(minutes=5)
    QueueEntry.objects.filter(kiosk=kiosk_id, StartTime__lt=five_minutes_ago).delete()
    
    return render(request, 'selectdistrict.html')

#THIS IS THE VIEW TO GET THE NEEDED DATA
def get_queue_data(request):
    try:
        kiosks = Kiosk.objects.all()
        kiosk_data = []
        for kiosk in kiosks:
            # Initialize the dictionary for this kiosk
            kiosk_info = {
                'KioskID': kiosk.KioskID,
                'user': None,
                'start_time': None,
            }
            
            # Check if kiosk has an associated QueueID and user
            if kiosk.QueueID_id and kiosk.QueueID.user:  # Using QueueID_id to avoid unnecessary DB hit
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

# Views for user login at the kiosk
def kiosk_login(request, kiosk_id):
    try:
        # Assuming kioskID is the relevant kiosk
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        kiosk_username = kiosk.QueueID.user.username if kiosk.QueueID else None
        if kiosk.QueueID:  # Ensure there is a user assigned to the kiosk
            # Use timezone.now() instead of now()
            time_elapsed_since_assignment = timezone.now() - (kiosk.TimeDuration or timezone.now())
            if time_elapsed_since_assignment.total_seconds() > 300:  # 5 minutes in seconds
                # If more than 5 minutes have passed, delete QueueEntry and reset Kiosk
                if kiosk.QueueID:
                    kiosk.QueueID.delete()  # This will delete the user from the queue
                    kiosk.QueueID = None
                    kiosk.KioskStatus = False
                    kiosk.TimeDuration = None
                    kiosk.save()
                messages.error(request, "Time exceeded. You have been removed from the queue.")
        else:
            # If no QueueID is associated, assign the user to this kiosk
            logged_in_username = request.session.get('logged_in_username')
            if logged_in_username:
                # Retrieve the user's queue entry
                queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
                # Associate the user's queue entry with this kiosk
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = timezone.now()
                kiosk.save()
            else:
                # If no user is logged in, delete the user from the queue database
                messages.error(request, "No user is currently logged in.")
                return HttpResponse(status=403)  # Return forbidden status

    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")

    # Proceed with login if within time limit and QueueID exists
    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': request.session.get('logged_in_username', None),
    }
    return render(request, f'kiosk{kiosk_id}_login.html', context)


#Views for logout in kiosk
@transaction.atomic
def kiosk_logout(request):
    if request.method == 'POST':
        # Get the username of the logged-in user
        logged_in_username = request.session.get('logged_in_username')
        if logged_in_username:
            try:
                # Retrieve the user's queue entry
                queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
                
                # Retrieve the associated kiosk using the foreign key relationship
                kiosk = get_object_or_404(Kiosk, QueueID=queue_entry)
                
                # Delete the queue entry and update the kiosk's QueueID to None
                queue_entry.delete()
                kiosk.QueueID = None
                kiosk.save()
                
                # Remove the logged-in username from the session
                del request.session['logged_in_username']
                
                # Redirect to the kiosk_logout URL
                return HttpResponseRedirect(reverse('kiosk_logout.html'))
            except QueueEntry.DoesNotExist:
                # Handle the case where no queue entry is found for the logged-in user
                pass
            except Kiosk.DoesNotExist:
                # Handle the case where no corresponding kiosk is found
                pass
    # Render the logout page template if the request is not a POST request
    return render(request, 'kiosk_logout.html')