from django.contrib import messages
from django.shortcuts import render, redirect
from .models import QueueVisitor, QueueEntry, Kiosk, Admin, Queue_Capacity, DistrictModules, TriviaQuestion, RewardPoints
import random
from django.utils import timezone
from datetime import timedelta
from django.http import HttpResponseRedirect, JsonResponse
from .models import QueueEntry, Kiosk
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
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
                    return redirect('login')
                
            except QueueVisitor.DoesNotExist:
                messages.error(request, 'Invalid username or password')
                return redirect('login')
    else:
        # If it's not a POST request, just show the login form
        return render(request, 'login.html')

# View for displaying the queue page
def queue(request):
    return render(request, 'queue.html')

def queue_list(request):
    is_admin = request.session.get('is_admin', False)
    
    # Update kiosk status and delete associated queue entries for timed-out sessions
    for kiosk in Kiosk.objects.filter(KioskStatus=True):
        if kiosk.TimeDuration and (timezone.now() - kiosk.TimeDuration > timedelta(minutes=5900)):
            if kiosk.QueueID:
                # Remove the user from the queue entry
                kiosk.QueueID.delete()
                # Decrement the queue count by 1
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
            queue_entry.EndTime = timezone.now()  # Update EndTime to match current time
            if queue_entry.StartTime:
                time_spent = timezone.now() - queue_entry.StartTime
                hours = int(time_spent.total_seconds() // 3600)
                minutes = int((time_spent.total_seconds() % 3600) // 60)
                queue_entry.EndTime = queue_entry.StartTime + timedelta(hours=hours, minutes=minutes)
            queue_entry.QueueStatus = 'IN KIOSK'
            queue_entry.save(update_fields=['QueueStatus', 'EndTime'])
            # Decrement the queue count by 1

    # Check if the current user is assigned to a kiosk
    logged_in_username = request.session.get('logged_in_username')
    if logged_in_username:
        assigned_kiosk = Kiosk.objects.filter(QueueID__user__username=logged_in_username).first()
        if assigned_kiosk:
            # If user is assigned to a kiosk, redirect to kiosk login page
            return redirect('kiosk_login', kiosk_id=assigned_kiosk.KioskID)

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
        'logged_in_username': logged_in_username,
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

        return redirect('kiosk_logout')  

    # Ensure that the kiosk data is refreshed
 
    
   
    context = {
        'kiosk_id': kiosk_id,
    }
    return render(request, 'selectdistrict.html',context)

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

def kiosk_login(request, kiosk_id):
    try:
        # Assuming kioskID is the relevant kiosk
        kiosk = Kiosk.objects.get(KioskID=kiosk_id)
        kiosk_username = kiosk.QueueID.user.username if kiosk.QueueID else None
        
        if not kiosk.QueueID:  # Ensure there is no user assigned to the kiosk
            # Check if a user is logged in
            logged_in_username = request.session.get('logged_in_username')
            if logged_in_username:
                # Retrieve the user's queue entry
                queue_entry = QueueEntry.objects.get(user__username=logged_in_username)
                # Associate the user's queue entry with this kiosk
                kiosk.QueueID = queue_entry
                kiosk.KioskStatus = True
                kiosk.TimeDuration = timezone.now()  # Start the timer
                kiosk.save()
            else:
                # If no user is logged in, return an error
                messages.error(request, "No user is currently logged in.")
                return HttpResponse(status=403)  # Return forbidden status

    except Kiosk.DoesNotExist:
        messages.error(request, "Invalid Kiosk.")

    # Proceed with login if no user is assigned to the kiosk
    context = {
        'kiosk_id': kiosk_id,
        'kiosk_username': kiosk_username,
        'logged_in_username': request.session.get('logged_in_username', None),
    }
    return render(request, f'kiosk{kiosk_id}_login.html', context)

#Views for logout in kiosk
@transaction.atomic
def kiosk_logout(request, kiosk_id):
    # Get the kiosk object from the database
    kiosk = get_object_or_404(Kiosk, KioskID=kiosk_id)

    # Check if the kiosk has an associated queue entry
    if kiosk.QueueID:
        # Get the associated queue entry
        queue_entry = kiosk.QueueID
        # Remove the associated queue entry
        queue_entry.delete()

    # Reset kiosk status and associated queue ID
    kiosk.KioskStatus = False
    kiosk.QueueID = None
    kiosk.TimeDuration = None
    kiosk.save()

    # Redirect or render as needed
    return render(request, 'kiosk_logout.html', {'kiosk_id': kiosk_id})

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


def no_user(request):
     return render(request, 'no_user.html')

def selectmunicipality1(request, kiosk_id):
    return render(request, 'selectmunicipality1.html',{'kiosk_id': kiosk_id})

def selectmunicipality2(request, kiosk_id):
    return render(request, 'selectmunicipality2.html',{'kiosk_id': kiosk_id})

def selectmunicipality3(request, kiosk_id):
    return render(request, 'selectmunicipality3.html',{'kiosk_id': kiosk_id})

def selectmunicipality4(request, kiosk_id):
    return render(request, 'selectmunicipality4.html',{'kiosk_id': kiosk_id})

def selectmunicipality5(request, kiosk_id):
    return render(request, 'selectmunicipality5.html',{'kiosk_id': kiosk_id})

def selectmunicipality6(request, kiosk_id):
    return render(request, 'selectmunicipality6.html',{'kiosk_id': kiosk_id})

def get_district_suffix(municipality):
    """
    This function takes a municipality name and returns the corresponding
    district suffix if found, else returns None.
    """
    suffix_to_municipalities = {
        'D1': ['NASUGBO', 'LIAN', 'TUY', 'BALAYAN', 'CALACA', 'CALATAGAN', 'LEMERY', 'TAAL'],
        'D2': ['SAN LUIS', 'BAUAN', 'SAN PASCUAL', 'MABINI', 'TINGLOY', 'LOBO'],
        'D3': ['STO.TOMAS', 'AGONCILLO', 'TALISAY', 'TANAUAN', 'MALVAR', 'SAN NICOLAS', 'BALETE', 'MATAAS NA KAHOY', 'STA. TERESITA', 'CUENCA', 'ALITAGTAG', 'LAUREL'],
        'D4': ['SAN JOSE', 'IBAAN', 'ROSARIO', 'TAYSAN', 'PADRE GARCIA', 'SAN JUAN'],
        'D5': ['BATANGAS'],  # Assuming "BATANGAS" refers to the city for clarity
        'D6': ['LIPA'],  # Assuming "LIPA" refers to the city for clarity
    }
    for suffix, municipalities in suffix_to_municipalities.items():
        if municipality.upper() in municipalities:
            return suffix
    return None

def get_modules_by_type_and_municipality(module_type, municipality):
    """
    This function filters DistrictModules based on module type, municipality,
    and the correct district suffix determined from the municipality name.
    """
    suffix = get_district_suffix(municipality)
    if not suffix:
        return None  # Municipality not found in the mapping

    # Filter modules based on type (t, f, c), municipality, and district suffix
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
    return render(request, 'module_tourist.html', {'modules': modules, 'municipality': municipality})

def module_food(request, kiosk_id, municipality):
    modules = get_modules_by_type_and_municipality('f', municipality)
    if modules is None:
        return render(request, 'error.html', {'message': 'Municipality not found.'})
    return render(request, 'module_food.html', {'modules': modules, 'municipality': municipality})

def module_craft(request, kiosk_id, municipality):
    modules = get_modules_by_type_and_municipality('c', municipality)
    if modules is None:
        return render(request, 'error.html', {'message': 'Municipality not found.'})
    return render(request, 'module_craft.html', {'modules': modules, 'municipality': municipality})


def selectmodule(request):
    municipality = request.GET.get('municipality', '')
    
    return render(request, 'selectmodule.html',{'municipality': municipality})

def calculate_points(remaining_seconds):
    # This is just an example, you can define your own logic
    return remaining_seconds // 10

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
    
def results_view(request):

    reward_points = request.session.get('game_session', {}).get('reward_points', 0)

    if 'game_session' in request.session:
        del request.session['game_session']
    
    return render(request, 'results.html', {
        'reward_points': reward_points
    })