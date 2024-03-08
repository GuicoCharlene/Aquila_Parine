from django.urls import path
from django.shortcuts import redirect
from .views import homepage, queue
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', lambda request: redirect('homepage/', permanent=True)), 
    path('homepage/', homepage, name='homepage'),
    path('queue/', queue, name='queue'),

]
