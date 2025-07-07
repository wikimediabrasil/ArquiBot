from django.urls import path
from . import views


urlpatterns = [
    path('', views.stats_page, name='stats_page'),
    path('api/stats/', views.combined_stats_api, name='combined_stats_api'),
    path('api/archived-citations/', views.ArchivedCitationList.as_view(), name='archived-citations'),
]