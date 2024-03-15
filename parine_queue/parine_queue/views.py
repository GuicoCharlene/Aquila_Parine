from django.contrib import messages
from django.shortcuts import render, redirect
from .models import QueueVisitor, QueueEntry, Kiosk, Admin, Queue_Capacity
from django.utils import timezone
from datetime import timedelta
from django.http import HttpResponseRedirect, JsonResponse
from .models import QueueEntry, Kiosk
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from .utils import ensure_kiosk_count


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
                    
                    # Creating or fetching the QueueEntry instance
                    queue_entry, created = QueueEntry.objects.get_or_create(user=visitor, defaults={'PriorityLevel': priority})
                    
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

#Views for the kiosk and queuelist
from django.utils import timezone

def queue_list(request):
    if request.method == 'POST' and 'logout_button' in request.POST:
        # Clear the user's queue entry if they log out
        user = request.session.get('logged_in_username')
        if user:
            QueueEntry.objects.filter(user__username=user).delete()
        return redirect('/kiosk_logout/')  # Redirect to logout page

    # Determine if the user is an admin
    is_admin = request.session.get('is_admin', False)

    # Fetch all queue entries ordered by priority
    queue_entries = QueueEntry.objects.select_related('user').order_by('PriorityLevel')

    # Fetch available kiosks
    available_kiosks = Kiosk.objects.filter(KioskStatus=False)

    # If there are queue entries and available kiosks, assign users to kiosks
    if queue_entries.exists() and available_kiosks.exists():
        # Iterate over queue entries to assign users to available kiosks
        for queue_entry in queue_entries:
            # Check if the user is already assigned to a kiosk
            if Kiosk.objects.filter(QueueID=queue_entry).exists():
                continue  # Skip assigning the user if they are already in a kiosk
            
            # If there are available kiosks, assign user to the first one
            available_kiosk = available_kiosks.first()

            if available_kiosk:  # Check if available_kiosk is not None
                # Update kiosk status and assign user
                available_kiosk.KioskStatus = True
                available_kiosk.QueueID = queue_entry
                available_kiosk.TimeDuration = timezone.now()  # Start the timer
                available_kiosk.save()

                # Update queue entry status and remove it from the queue
                queue_entry.QueueStatus = 'IN KIOSK'
                queue_entry.save()

                # Remove the assigned kiosk from the list of available kiosks
                available_kiosks = available_kiosks.exclude(pk=available_kiosk.pk)

                # Remove user from the queue list
                queue_entries = queue_entries.exclude(pk=queue_entry.pk)

    # Update kiosk status for users who have finished
    for kiosk in Kiosk.objects.filter(KioskStatus=True, TimeDuration__lte=timezone.now()):
        kiosk.KioskStatus = False
        kiosk.QueueID = None
        kiosk.save(update_fields=['KioskStatus', 'QueueID'])

    # Fetch all kiosks data
    kiosks_data = []
    for kiosk in Kiosk.objects.all():
        if kiosk.KioskStatus:
            # Calculate time spent inside the kiosk in minutes
            time_spent = (timezone.now() - kiosk.TimeDuration).total_seconds() / 60
            kiosks_data.append({'KioskID': kiosk.KioskID, 'user': kiosk.QueueID.user.username, 'time_spent': time_spent})
        else:
            # If the kiosk is available, display "AVAILABLE"
            kiosks_data.append({'KioskID': kiosk.KioskID, 'status': 'AVAILABLE'})

    context = {
        'queue_entries': queue_entries,
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

        # Redirect to the logout page or any desired URL
        return redirect('/kiosk_logout/')  

    # # Remove QueueID for users who entered the queue more than 5 minutes ago
    # five_minutes_ago = timezone.now() - timezone.timedelta(minutes=5)
    # QueueEntry.objects.filter(kiosk=kiosk_id, StartTime__lt=five_minutes_ago).delete()

    return render(request, 'selectdistrict.html')


def get_queue_data(request):
    # Get queue list data
    queue_entries = QueueEntry.objects.all()
    queue_data = [{'username': entry.user.username} for entry in queue_entries]

    # Get kiosk status data
    kiosks = Kiosk.objects.all()
    kiosk_data = []
    for kiosk in kiosks:
        if kiosk.KioskStatus:
            # Calculate time spent inside the kiosk in minutes
            time_spent = (timezone.now() - kiosk.TimeDuration).total_seconds() / 60
            kiosk_data.append({
                'kiosk_id': kiosk.KioskID,
                'user': kiosk.user.username if kiosk.user else None,
                'time_spent': time_spent
            })
        else:
            kiosk_data.append({'kiosk_id': kiosk.KioskID, 'user': None, 'time_spent': None})

    return JsonResponse({'queue_entries': queue_data, 'kiosk_data': kiosk_data})

def kiosk_login(request, kiosk_id):
    try:
        # Assuming kioskID is the relevant kiosk
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        kiosk_username = kiosk.QueueID.user.username if kiosk.QueueID else None
        
        # Check if the kiosk timer has started and the user hasn't logged in within 5 minutes
        if kiosk.TimeDuration and timezone.now() - kiosk.TimeDuration > timedelta(minutes=5):
            # Remove the user from the queue entry associated with this kiosk
            if kiosk.QueueID:
                queue_entry = kiosk.QueueID
                queue_entry.delete()
                kiosk.QueueID = None
                kiosk.KioskStatus = False  # Set KioskStatus back to 0
                kiosk.save()
            messages.error(request, 'You have exceeded the login time limit. Please try again later.')
            return redirect('homepage')
        
        # Start the timer if it hasn't started already
        if not kiosk.TimeDuration:
            kiosk.start_timer()
    except Kiosk.DoesNotExist:
        kiosk_username = None

    context = {
        'kiosk_username': kiosk_username,
        'logged_in_username': request.session.get('logged_in_username', None),
    }
    return render(request, f'kiosk{kiosk_id}_login.html', context)

def kiosk_logout(request):
    if request.method == 'POST':
        # Get the username of the logged-in user
        logged_in_username = request.session.get('logged_in_username')
        if logged_in_username:
            try:
                # Retrieve the user's queue entry
                queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
                
                # Check if the queue entry has a corresponding kiosk and update its QueueID to None
                kiosk = get_object_or_404(Kiosk, QueueID=queue_entry)
                kiosk.QueueID = None
                kiosk.save()
                
                # Delete the queue entry
                queue_entry.delete()
                
                # Remove the logged-in username from the session
                del request.session['logged_in_username']
                
                # Redirect to kiosk_logout.html
                return HttpResponseRedirect(reverse('kiosk_logout'))
            except QueueEntry.DoesNotExist:
                # Handle the case where no queue entry is found for the logged-in user
                pass
            except Kiosk.DoesNotExist:
                # Handle the case where no corresponding kiosk is found
                pass
    # Render the logout page template if the request is not a POST request
    return render(request, 'kiosk_logout.html')