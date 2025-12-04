from django.urls import path
from .views import receive_alarm

urlpatterns = [
    path('webhook/', receive_alarm, name='receive_alarm'),
]
