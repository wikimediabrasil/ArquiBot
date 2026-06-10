from django.urls import path
from . import views


urlpatterns = [
    path('logs/', views.logs, name='logs'),
    path('', views.home, name='home'),
    path('stats/<int:id>/', views.stats, name='stats'),
]
