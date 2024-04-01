from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from . import views
from .views import login, homepage, queue, queue_list, adminpage, selectdistrict, update_queue_capacity, kiosk_logout, kiosk_login, get_queue_data, admin_district_1, history, take_quiz, results_view
from .views import admin_district_2, admin_district_3, admin_district_4, admin_district_5, admin_district_6, selectmunicipality1, selectmunicipality2, selectmunicipality3, selectmunicipality4, selectmunicipality5, selectmunicipality6, selectmodule, module_tourist, module_food, module_craft, quiz
from .views import admin_module_tourist, admin_module_food, admin_module_craft, save_module_changes, done_quiz


urlpatterns = [
    path('login/', login, name='login'),
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
    path('kiosk_logout/<int:kiosk_id>/', kiosk_logout, name='kiosk_logout'),
    path('kiosk_login/<int:kiosk_id>/', kiosk_login, name='kiosk_login'),
    path('kiosk_login/<int:kiosk_id>/selectdistrict/', views.selectdistrict, name='selectdistrict'),

    path('get_queue_data/', get_queue_data, name='get_queue_data'),
    
    path('delete_queue_kiosk_data/<int:kioskId>/', views.delete_queue_kiosk_data, name='delete_queue_kiosk_data'),
    # path('update_queue_status/<int:kiosk_id>/', views.update_queue_status, name='update_queue_status'),
    path('kiosk_login/<int:kiosk_id>/selectmunicipality1/', selectmunicipality1, name='selectmunicipality1'),
    path('kiosk_login/<int:kiosk_id>/selectmunicipality2/', selectmunicipality2, name='selectmunicipality2'),
    path('kiosk_login/<int:kiosk_id>/selectmunicipality3/', selectmunicipality3, name='selectmunicipality3'),
    path('kiosk_login/<int:kiosk_id>/selectmunicipality4/', selectmunicipality4, name='selectmunicipality4'),
    path('kiosk_login/<int:kiosk_id>/selectmunicipality5/', selectmunicipality5, name='selectmunicipality5'),
    path('kiosk_login/<int:kiosk_id>/selectmunicipality6/', selectmunicipality6, name='selectmunicipality6'),
    
    path('kiosk_login/<int:kiosk_id>/module_tourist/<str:municipality>/', module_tourist, name='module_tourist'),
    path('kiosk_login/<int:kiosk_id>/module_food/<str:municipality>/', module_food, name='module_food'),
    path('kiosk_login/<int:kiosk_id>/module_craft/<str:municipality>/', module_craft, name='module_craft'),
    
    # path('selectmodule/', selectmodule, name='selectmodule'),
    path('take_quiz/', take_quiz, name='take_quiz'),
    path('take_quiz/quiz/', quiz, name='quiz'),
    
    path('quiz/', quiz, name='quiz'),
    path('results/', results_view, name='results'),
    
    path('adminpage/history/', history, name='history'),
    path('adminpage/module_tourist/<str:municipality>/', admin_module_tourist, name='admin_module_tourist'),
    path('adminpage/module_food/<str:municipality>/', admin_module_food, name='admin_module_food'),
    path('adminpage/module_craft/<str:municipality>/', admin_module_craft, name='admin_module_craft'),

    path('save_module_changes/', save_module_changes, name='save_module_changes'),
    path('done_quiz/', done_quiz, name='done_quiz'),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
