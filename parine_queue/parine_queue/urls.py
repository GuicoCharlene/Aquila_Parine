from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from . import views
from .utils import ensure_kiosk_count
from .views import landing, homepage, queue, queue_list, adminpage, selectdistrict, update_queue_capacity, kiosk_logout, kiosk_login, trigger_kiosk_count, get_queue_data, admin_district_1
from .views import admin_district_2, admin_district_3, admin_district_4, admin_district_5, admin_district_6, selectmunicipality1, selectmunicipality2, selectmunicipality3, selectmunicipality4, selectmunicipality5, selectmunicipality6, selectmodule, module_tourist, module_food, module_craft

ensure_kiosk_count()

urlpatterns = [
    path('landing/', landing, name='landing'),
    path('homepage/', homepage, name='homepage'),
    path('queue/', queue, name='queue'),
    path('queue_list/', queue_list, name='queue_list'),
    
    path('adminpage/', adminpage, name='adminpage'),
    path('adminpage/admin_district_1/', admin_district_1, name='admin_district_1'),
    path('adminpage/admin_district_2/', admin_district_2, name='admin_district_2'),
    path('adminpage/admin_district_3/', admin_district_3, name='admin_district_3'),
    path('adminpage/admin_district_4/', admin_district_4, name='admin_district_4'),
    path('adminpage/admin_district_5/', admin_district_5, name='admin_district_5'),
    path('adminpage/admin_district_6/', admin_district_6, name='admin_district_6'),

    path('update_queue_capacity/', update_queue_capacity, name='update_queue_capacity'),  
    path('trigger-kiosk-count/', trigger_kiosk_count, name='trigger_kiosk_count'),
    path('kiosk_logout/', kiosk_logout, name='kiosk_logout'),
    path('kiosk_login/<int:kiosk_id>/', kiosk_login, name='kiosk_login'),
    path('kiosk_login/<int:kiosk_id>/selectdistrict/', views.selectdistrict, name='selectdistrict'),

    path('get_queue_data/', get_queue_data, name='get_queue_data'),
    
    path('selectmunicipality1/', selectmunicipality1, name='selectmunicipality1'),
    path('selectmunicipality2/', selectmunicipality2, name='selectmunicipality2'),
    path('selectmunicipality3/', selectmunicipality3, name='selectmunicipality3'),
    path('selectmunicipality4/', selectmunicipality4, name='selectmunicipality4'),
    path('selectmunicipality5/', selectmunicipality5, name='selectmunicipality5'),
    path('selectmunicipality6/', selectmunicipality6, name='selectmunicipality6'),
    
    path('selectmodule/module_tourist/', module_tourist, name='module_tourist'),
    path('selectmodule/module_food/', module_food, name='module_food'),
    path('selectmodule/module_craft/', module_craft, name='module_craft'),
    
    path('selectmodule/', selectmodule, name='selectmodule'),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
