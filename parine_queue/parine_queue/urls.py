from django.urls import path
from . import views
from .utils import ensure_kiosk_count
from .views import landing, homepage, queue, queue_list, adminpage, selectdistrict, update_queue_capacity, kiosk_logout, kiosk_login, trigger_kiosk_count, get_queue_data

ensure_kiosk_count()

urlpatterns = [
    path('landing/', landing, name='landing'),
    path('homepage/', homepage, name='homepage'),
    path('queue/', queue, name='queue'),
    path('queue_list/', queue_list, name='queue_list'),
    path('adminpage/', adminpage, name='adminpage'),
    path('update_queue_capacity/', update_queue_capacity, name='update_queue_capacity'),  
    path('trigger-kiosk-count/', trigger_kiosk_count, name='trigger_kiosk_count'),
    path('kiosk_logout/', kiosk_logout, name='kiosk_logout'),
    path('kiosk_login/<int:kiosk_id>/', views.kiosk_login, name='kiosk_login'),
    path('kiosk_login/<int:kiosk_id>/selectdistrict/', views.selectdistrict, name='selectdistrict'),
    path('get_queue_data/', get_queue_data, name='get_queue_data'),
]
