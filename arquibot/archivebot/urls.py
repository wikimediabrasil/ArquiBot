from django.urls import path
from . import views


urlpatterns = [
    path('', views.stats_page, name='stats_page'),
]
