from django.urls import path
from . import views


urlpatterns = [
    path('logs/', views.logs, name='logs'),
    path('logs/article/<int:id>/', views.logs_article, name='logs_article'),
    path('', views.home, name='home'),
    path('stats/', views.stats, name='stats'),
]
