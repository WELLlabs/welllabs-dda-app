from django.urls import path
from .views import watershed_lookup

urlpatterns = [
    path('watershed/', watershed_lookup),
]
