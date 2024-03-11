from django.urls import path
from .views import landing, homepage, queue, queue_list

urlpatterns = [
    path('landing/', landing, name='landing'),
    path('homepage/', homepage, name='homepage'),
    path('queue/', queue, name='queue'),
    path('queue_list/', queue_list, name='queue_list'),
]
